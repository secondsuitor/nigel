"""
Export all posts and categories from the local database to a JSON file.

Run this on the development machine after the WordPress import to produce
a portable snapshot that can be loaded on any server with load_posts.py.

Usage:
  cd /home/kriminel/Documents/coding/website
  source venv/bin/activate
  python export_posts.py

Output: posts_export.json in the project root.

The JSON structure is:
  {
    "exported_at": "2026-04-04T22:00:00",
    "categories": [ { "slug": "...", "name": "...", "description": "..." }, … ],
    "posts": [
      {
        "title": "…", "slug": "…", "content": "…", "excerpt": "…",
        "status": "published", "post_type": "post",
        "published_at": "2011-10-12T01:55:45",
        "created_at": "…", "updated_at": "…",
        "wordpress_id": 9, "wordpress_date": "…", "wordpress_url": "…",
        "meta_description": null, "featured_image": null,
        "categories": ["slug-one", "slug-two"]
      }, …
    ]
  }

Category membership is stored as a list of category slugs on each post so
the file is self-contained and order-independent on import.
"""

import json
import sys
from datetime import datetime

from app import create_app, db
from app.models import Category, Post


OUTPUT_FILE = "posts_export.json"


def dt_to_str(value):
  """
  Serialise a datetime to an ISO-8601 string, or return None.

  The JSON spec has no date type so we store datetimes as strings and parse
  them back on import.
  """
  if value is None:
    return None
  return value.strftime('%Y-%m-%dT%H:%M:%S')


def export():
  """
  Query all categories and posts, write them to OUTPUT_FILE as JSON.

  Returns 0 on success.
  """
  categories = db.session.execute(db.select(Category)).scalars().all()
  category_data = [
    {
      "slug": cat.slug,
      "name": cat.name,
      "description": cat.description,
    }
    for cat in categories
  ]

  posts = db.session.execute(
    db.select(Post).order_by(Post.published_at.asc())
  ).scalars().all()

  post_data = []
  for post in posts:
    post_data.append({
      "title": post.title,
      "slug": post.slug,
      "content": post.content,
      "excerpt": post.excerpt,
      "status": post.status,
      "post_type": post.post_type,
      "published_at": dt_to_str(post.published_at),
      "created_at": dt_to_str(post.created_at),
      "updated_at": dt_to_str(post.updated_at),
      "wordpress_id": post.wordpress_id,
      "wordpress_date": dt_to_str(post.wordpress_date),
      "wordpress_url": post.wordpress_url,
      "meta_description": post.meta_description,
      "featured_image": post.featured_image,
      # Store as slugs so the file stays readable and portable.
      "categories": [cat.slug for cat in post.categories],
    })

  payload = {
    "exported_at": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'),
    "categories": category_data,
    "posts": post_data,
  }

  with open(OUTPUT_FILE, 'w', encoding='utf-8') as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2)

  print(f"Exported {len(post_data)} posts and {len(category_data)} categories")
  print(f"Output: {OUTPUT_FILE}")
  return 0


if __name__ == '__main__':
  app = create_app()
  with app.app_context():
    sys.exit(export())
