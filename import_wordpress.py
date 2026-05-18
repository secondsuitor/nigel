"""
One-time import script: reads the secondsuitor WordPress MySQL backup and
inserts published posts and their categories into the Flask app database.

The backup is a MySQL dump — we parse it with regex rather than executing it,
because the syntax is MySQL-specific and the target database is SQLite (dev)
or PostgreSQL (prod).

Usage:
  cd /home/kriminel/Documents/coding/website
  source venv/bin/activate
  python import_wordpress.py

The script is idempotent: posts are matched by wordpress_id, so re-running
will skip any post already in the database.  Categories are matched by slug.

Design decisions:
  - bleach sanitises post_content before storage (same rules as routes.py)
  - post_name (WP slug) is used directly; a numeric suffix is appended if it
    conflicts with an existing slug
  - published_at is taken from post_date (local time stored by WordPress)
  - created_at and updated_at are set from post_date and post_modified
  - Only post_type='post' and post_status='publish' rows are imported
"""

import sys
from datetime import datetime

import bleach

from app import create_app, db
from app.models import Category, Post


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SQL_FILE = (
  "from_secondsuitor_dot_com/"
  "backup-secondsuitor-20250608-114356-GARA1jQIh4oNUBdFUR8RWXjjzLh3Ma.sql"
)

TABLE_PREFIX = "s81sjp_"

# Mirrors the ALLOWED_TAGS / ALLOWED_ATTRS in routes.py so imported content
# is cleaned with the same rules as admin-entered content.
ALLOWED_TAGS = frozenset([
  'a', 'aside', 'b', 'blockquote', 'br', 'del', 'em',
  'figure', 'figcaption',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'i', 'img', 'li', 'ol', 'p', 'strong', 'sub', 'sup',
  'template', 'u', 'ul',
])

ALLOWED_ATTRS = {
  '*': ['class'],
  'a': ['href', 'title'],
  'img': ['src', 'alt', 'width', 'height', 'loading'],
}


# ---------------------------------------------------------------------------
# SQL parsing helpers
# ---------------------------------------------------------------------------

def unescape_sql_string(value):
  """
  Reverse MySQL string escaping from a VALUES token.

  MySQL uses backslash escapes inside quoted strings.  Python's re module
  gives us the raw bytes with those backslashes intact, so we convert the
  most common ones back to real characters.
  """
  value = value.replace("\\'", "'")
  value = value.replace('\\"', '"')
  value = value.replace('\\n', '\n')
  value = value.replace('\\r', '\r')
  value = value.replace('\\t', '\t')
  value = value.replace('\\\\', '\\')
  return value


def parse_sql_values_line(line):
  """
  Extract the tuple of column values from one INSERT INTO … VALUES (…); line.

  MySQL dumps quote every value with double quotes in this backup, use NULL
  for null values, and separate columns with commas.  Because post_content
  can contain commas and even newlines (the INSERT is one physical line in
  this backup), we parse character-by-character instead of using str.split.

  Returns a list of strings (with SQL escaping reversed) or None if the line
  cannot be parsed.
  """
  paren_start = line.find('(')
  if paren_start == -1:
    return None

  tokens = []
  current = []
  i = paren_start + 1
  in_string = False
  quote_char = None

  while i < len(line):
    ch = line[i]

    if in_string:
      if ch == '\\':
        # Consume the backslash and the following character raw so the
        # unescape step later handles them.
        current.append(ch)
        i += 1
        if i < len(line):
          current.append(line[i])
      elif ch == quote_char:
        in_string = False
      else:
        current.append(ch)
    else:
      if ch in ('"', "'"):
        in_string = True
        quote_char = ch
      elif ch == ',':
        tokens.append(unescape_sql_string(''.join(current)))
        current = []
      elif ch in (')', ';'):
        tokens.append(unescape_sql_string(''.join(current)))
        break
      elif line[i:i + 4] == 'NULL':
        tokens.append(None)
        current = []
        i += 3  # skip 'ULL'; loop will advance past the final 'L'
      else:
        current.append(ch)
    i += 1

  return tokens if tokens else None


def parse_datetime(value):
  """
  Parse a MySQL datetime string like '2011-10-12 01:55:45' to a Python
  datetime.  Returns None for empty strings or the MySQL zero-datetime.
  """
  if not value or value == '0000-00-00 00:00:00':
    return None
  try:
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
  except ValueError:
    return None


# ---------------------------------------------------------------------------
# Data collection — stream through the SQL file once per table
# ---------------------------------------------------------------------------

def collect_posts(sql_file):
  """
  Read the SQL file and return a list of dicts for every published post.

  Each dict has keys matching the Post model fields.  Content is bleach-
  cleaned at this stage.  The wp_id key is the original WordPress post ID
  used for de-duplication and relationship lookups.
  """
  insert_prefix = f"INSERT INTO `{TABLE_PREFIX}posts`"
  posts = []

  with open(sql_file, 'r', encoding='utf-8', errors='replace') as fh:
    for line in fh:
      if not line.startswith(insert_prefix):
        continue

      cols = parse_sql_values_line(line)
      if not cols or len(cols) < 23:
        continue

      # Column order confirmed from CREATE TABLE at line 35941 of the backup.
      post_type = cols[20]
      post_status = cols[7]

      if post_type != 'post' or post_status != 'publish':
        continue

      wp_id = int(cols[0])
      post_date = parse_datetime(cols[2])
      post_modified = parse_datetime(cols[14])
      slug = (cols[11] or '').strip() or f"post-{wp_id}"
      title = (cols[5] or '').strip() or f"(untitled {wp_id})"
      content = bleach.clean(cols[4] or '', tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)
      excerpt = (cols[6] or '').strip()
      guid = (cols[18] or '').strip()

      posts.append({
        'wordpress_id': wp_id,
        'title': title,
        'slug': slug,
        'content': content,
        'excerpt': excerpt or None,
        'status': 'published',
        'post_type': 'post',
        'published_at': post_date,
        'created_at': post_date or datetime.utcnow(),
        'updated_at': post_modified or post_date or datetime.utcnow(),
        'wordpress_date': post_date,
        'wordpress_url': guid or None,
      })

  return posts


def collect_categories(sql_file):
  """
  Return a dict mapping term_taxonomy_id -> {'name': str, 'slug': str}.

  Only rows with taxonomy='category' from s81sjp_term_taxonomy are included.
  Term names and slugs come from s81sjp_terms.
  """
  # Step 1: read all terms — term_id -> {name, slug}
  terms = {}
  terms_prefix = f"INSERT INTO `{TABLE_PREFIX}terms`"
  with open(sql_file, 'r', encoding='utf-8', errors='replace') as fh:
    for line in fh:
      if not line.startswith(terms_prefix):
        continue
      cols = parse_sql_values_line(line)
      if not cols or len(cols) < 3:
        continue
      # Columns: term_id, name, slug, term_group
      terms[int(cols[0])] = {'name': (cols[1] or '').strip(), 'slug': (cols[2] or '').strip()}

  # Step 2: read term_taxonomy — only category rows
  # Columns: term_taxonomy_id, term_id, taxonomy, description, parent, count
  categories = {}
  tt_prefix = f"INSERT INTO `{TABLE_PREFIX}term_taxonomy`"
  with open(sql_file, 'r', encoding='utf-8', errors='replace') as fh:
    for line in fh:
      if not line.startswith(tt_prefix):
        continue
      cols = parse_sql_values_line(line)
      if not cols or len(cols) < 3:
        continue
      term_taxonomy_id = int(cols[0])
      term_id = int(cols[1])
      taxonomy = cols[2]
      if taxonomy != 'category':
        continue
      if term_id in terms:
        categories[term_taxonomy_id] = terms[term_id]

  return categories


def collect_relationships(sql_file):
  """
  Return a dict mapping object_id (WordPress post ID) ->
  list of term_taxonomy_ids.

  The s81sjp_term_relationships table has columns:
    object_id, term_taxonomy_id, term_order
  """
  relationships = {}
  rel_prefix = f"INSERT INTO `{TABLE_PREFIX}term_relationships`"
  with open(sql_file, 'r', encoding='utf-8', errors='replace') as fh:
    for line in fh:
      if not line.startswith(rel_prefix):
        continue
      cols = parse_sql_values_line(line)
      if not cols or len(cols) < 2:
        continue
      object_id = int(cols[0])
      term_taxonomy_id = int(cols[1])
      relationships.setdefault(object_id, []).append(term_taxonomy_id)

  return relationships


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def ensure_unique_slug(base_slug, existing_slugs):
  """
  Return a slug that does not collide with the existing_slugs set.

  If base_slug is already unique it is returned unchanged.  Otherwise a
  numeric suffix (-2, -3, …) is appended until a free value is found.
  The chosen slug is added to existing_slugs so subsequent calls within
  the same import run stay consistent.
  """
  slug = base_slug
  counter = 2
  while slug in existing_slugs:
    slug = f"{base_slug}-{counter}"
    counter += 1
  existing_slugs.add(slug)
  return slug


def run_import():
  """
  Main entry point: parse the backup, then write to the database.

  Prints a progress summary and returns an exit code (0 = success).
  """
  print(f"Reading {SQL_FILE} ...")

  posts_data = collect_posts(SQL_FILE)
  print(f"  Found {len(posts_data)} published posts in backup")

  categories_map = collect_categories(SQL_FILE)
  print(f"  Found {len(categories_map)} categories in backup")

  relationships = collect_relationships(SQL_FILE)
  print(f"  Found relationships for {len(relationships)} post IDs")

  # Gather what already exists in the database so we can be idempotent.
  existing_wp_ids = {
    row[0] for row in db.session.execute(
      db.select(Post.wordpress_id).where(Post.wordpress_id.isnot(None))
    ).all()
  }
  existing_slugs = {
    row[0] for row in db.session.execute(db.select(Post.slug)).all()
  }

  # Ensure all referenced categories exist in the database.
  # Map term_taxonomy_id -> Category ORM object.
  category_objects = {}
  categories_created = 0

  for ttid, cat_info in categories_map.items():
    cat_slug = cat_info['slug']
    cat_name = cat_info['name']

    # Skip 'Uncategorized' — it adds noise and has no editorial value.
    if cat_slug == 'uncategorized':
      continue

    existing_cat = db.session.execute(
      db.select(Category).where(Category.slug == cat_slug)
    ).scalar_one_or_none()

    if existing_cat:
      category_objects[ttid] = existing_cat
    else:
      new_cat = Category(name=cat_name, slug=cat_slug)
      db.session.add(new_cat)
      db.session.flush()  # assign new_cat.category_id before linking
      category_objects[ttid] = new_cat
      categories_created += 1

  # Import posts.
  posts_imported = 0
  posts_skipped = 0

  for post_data in posts_data:
    wp_id = post_data['wordpress_id']

    if wp_id in existing_wp_ids:
      posts_skipped += 1
      continue

    unique_slug = ensure_unique_slug(post_data['slug'], existing_slugs)

    post = Post(
      title=post_data['title'],
      slug=unique_slug,
      content=post_data['content'],
      excerpt=post_data['excerpt'],
      status=post_data['status'],
      post_type=post_data['post_type'],
      published_at=post_data['published_at'],
      created_at=post_data['created_at'],
      updated_at=post_data['updated_at'],
      wordpress_date=post_data['wordpress_date'],
      wordpress_id=wp_id,
      wordpress_url=post_data['wordpress_url'],
    )

    # Attach categories from the term_relationships table.
    for ttid in relationships.get(wp_id, []):
      if ttid in category_objects:
        post.categories.append(category_objects[ttid])

    db.session.add(post)
    posts_imported += 1

  db.session.commit()

  print()
  print("Import complete:")
  print(f"  Posts imported : {posts_imported}")
  print(f"  Posts skipped  : {posts_skipped} (already in database)")
  print(f"  Categories new : {categories_created}")
  return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
  app = create_app()
  with app.app_context():
    sys.exit(run_import())