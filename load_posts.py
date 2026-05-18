"""
Load posts and categories from a JSON export into the database.

Run this on the production server (or any target environment) to populate
the database from a posts_export.json produced by export_posts.py.

Usage:
  python load_posts.py                         # reads posts_export.json
  python load_posts.py /path/to/export.json    # reads from a given path

The script is idempotent:
  - Categories are matched by slug; existing ones are left unchanged.
  - Posts are matched by wordpress_id (if set) or by slug.
    Any post already in the database is skipped.

After a successful run you will see:
  Posts loaded  : 182
  Posts skipped : 0  (already in database)
  Categories new: 7
"""

import json
import sys
from datetime import datetime

from app import create_app, db
from app.models import Category, Post


def parse_dt(value):
  """
  Parse an ISO-8601 datetime string from the export file.

  Returns None for null or missing values so nullable datetime columns
  are handled cleanly.
  """
  if not value:
    return None
  try:
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')
  except ValueError:
    return None


def ensure_unique_slug(base_slug, existing_slugs):
  """
  Return a slug that does not collide with existing_slugs.

  If base_slug is already free it is returned unchanged.  Otherwise
  a numeric suffix (-2, -3, …) is appended until a free value is found.
  The chosen slug is added to existing_slugs so calls within the same
  run stay consistent.
  """
  slug = base_slug
  counter = 2
  while slug in existing_slugs:
    slug = f"{base_slug}-{counter}"
    counter += 1
  existing_slugs.add(slug)
  return slug


def load(json_file):
  """
  Read json_file and insert its contents into the database.

  Returns 0 on success, 1 on file-not-found or parse error.
  """
  try:
    with open(json_file, 'r', encoding='utf-8') as fh:
      payload = json.load(fh)
  except FileNotFoundError:
    print(f"ERROR: file not found: {json_file}")
    return 1
  except json.JSONDecodeError as exc:
    print(f"ERROR: could not parse JSON: {exc}")
    return 1

  exported_at = payload.get("exported_at", "unknown")
  print(f"Loading export from {exported_at}")
  print(f"  {len(payload['posts'])} posts, {len(payload['categories'])} categories")

  # --- Categories -----------------------------------------------------------
  # Build slug -> Category map so posts can look up their categories quickly.
  category_map = {}
  categories_created = 0

  for cat_data in payload["categories"]:
    slug = cat_data["slug"]
    existing = db.session.execute(
      db.select(Category).where(Category.slug == slug)
    ).scalar_one_or_none()

    if existing:
      category_map[slug] = existing
    else:
      new_cat = Category(
        slug=slug,
        name=cat_data["name"],
        description=cat_data.get("description"),
      )
      db.session.add(new_cat)
      db.session.flush()  # assign category_id before posts reference it
      category_map[slug] = new_cat
      categories_created += 1

  # --- Posts ----------------------------------------------------------------
  existing_wp_ids = {
    row[0] for row in db.session.execute(
      db.select(Post.wordpress_id).where(Post.wordpress_id.isnot(None))
    ).all()
  }
  existing_slugs = {
    row[0] for row in db.session.execute(db.select(Post.slug)).all()
  }

  posts_loaded = 0
  posts_skipped = 0

  for post_data in payload["posts"]:
    wp_id = post_data.get("wordpress_id")

    # Skip if already present (match by wordpress_id, fall back to slug).
    if wp_id and wp_id in existing_wp_ids:
      posts_skipped += 1
      continue
    if not wp_id and post_data["slug"] in existing_slugs:
      posts_skipped += 1
      continue

    unique_slug = ensure_unique_slug(post_data["slug"], existing_slugs)

    post = Post(
      title=post_data["title"],
      slug=unique_slug,
      content=post_data["content"],
      excerpt=post_data.get("excerpt"),
      status=post_data["status"],
      post_type=post_data["post_type"],
      published_at=parse_dt(post_data.get("published_at")),
      created_at=parse_dt(post_data.get("created_at")) or datetime.utcnow(),
      updated_at=parse_dt(post_data.get("updated_at")) or datetime.utcnow(),
      wordpress_id=wp_id,
      wordpress_date=parse_dt(post_data.get("wordpress_date")),
      wordpress_url=post_data.get("wordpress_url"),
      meta_description=post_data.get("meta_description"),
      featured_image=post_data.get("featured_image"),
    )

    for cat_slug in post_data.get("categories", []):
      if cat_slug in category_map:
        post.categories.append(category_map[cat_slug])

    db.session.add(post)
    posts_loaded += 1

  db.session.commit()

  print()
  print("Load complete:")
  print(f"  Posts loaded  : {posts_loaded}")
  print(f"  Posts skipped : {posts_skipped} (already in database)")
  print(f"  Categories new: {categories_created}")
  return 0


if __name__ == '__main__':
  # Accept an optional path argument; default to posts_export.json.
  json_file = sys.argv[1] if len(sys.argv) > 1 else "posts_export.json"
  app = create_app()
  with app.app_context():
    sys.exit(load(json_file))
