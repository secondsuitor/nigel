"""
Migration: add bluesky_uri column to the post table.

Stores the AT Protocol URI returned after a successful Bluesky cross-post,
e.g. at://did:plc:<id>/app.bsky.feed.post/<rkey>.  NULL means the post has
not been sent to Bluesky yet.

Safe to run multiple times — idempotent on both SQLite (dev) and
PostgreSQL 11 (Gandi.net prod).

Usage:
  cd /home/kriminel/Documents/coding/website
  source venv/bin/activate
  python migrations/add_bluesky_uri.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app import create_app, db


def run():
  """Add bluesky_uri VARCHAR(200) NULL to the post table if not present."""
  app = create_app()
  with app.app_context():
    with db.engine.connect() as conn:
      dialect = db.engine.dialect.name

      if dialect == 'sqlite':
        result = conn.execute(text("PRAGMA table_info('post')"))
        columns = [row[1] for row in result.fetchall()]
        if 'bluesky_uri' in columns:
          print('Column already exists — nothing to do.')
          return 0
        conn.execute(text(
          "ALTER TABLE post ADD COLUMN bluesky_uri VARCHAR(200) NULL"
        ))
        conn.commit()

      elif dialect == 'postgresql':
        result = conn.execute(text("""
          SELECT column_name FROM information_schema.columns
          WHERE table_name = 'post' AND column_name = 'bluesky_uri'
        """))
        if result.fetchone():
          print('Column already exists — nothing to do.')
          return 0
        conn.execute(text(
          "ALTER TABLE post ADD COLUMN bluesky_uri VARCHAR(200) NULL"
        ))
        conn.commit()

      else:
        print(f'Unsupported dialect: {dialect}')
        return 1

      print('Migration complete: bluesky_uri column added to post table.')
      return 0


if __name__ == '__main__':
  sys.exit(run())
