"""
Migration: add totp_secret column to the user table.

Safe to run multiple times — uses IF NOT EXISTS / try-except so it is
idempotent on both SQLite (dev) and PostgreSQL (prod).

Usage:
  cd /home/kriminel/Documents/coding/website
  source venv/bin/activate
  python migrations/add_totp_secret.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app, db


def run():
  """Add totp_secret VARCHAR(64) NULL to the user table if not present."""
  app = create_app()
  with app.app_context():
    # SQLite does not support IF NOT EXISTS on ADD COLUMN, so we check
    # for the column's existence first via PRAGMA / information_schema.
    with db.engine.connect() as conn:
      dialect = db.engine.dialect.name

      if dialect == 'sqlite':
        result = conn.execute(text("PRAGMA table_info('user')"))
        columns = [row[1] for row in result.fetchall()]
        if 'totp_secret' in columns:
          print("Column already exists — nothing to do.")
          return 0
        conn.execute(text(
          "ALTER TABLE \"user\" ADD COLUMN totp_secret VARCHAR(64) NULL"
        ))
        conn.commit()

      elif dialect == 'postgresql':
        result = conn.execute(text("""
          SELECT column_name FROM information_schema.columns
          WHERE table_name = 'user' AND column_name = 'totp_secret'
        """))
        if result.fetchone():
          print("Column already exists — nothing to do.")
          return 0
        conn.execute(text(
          'ALTER TABLE "user" ADD COLUMN totp_secret VARCHAR(64) NULL'
        ))
        conn.commit()

      else:
        print(f"Unsupported dialect: {dialect}")
        return 1

    print("Migration complete: totp_secret column added.")
    return 0


if __name__ == '__main__':
  sys.exit(run())
