"""
Migration: add content-type tables and extend Footnote.

Changes applied:
  - Add columns to footnote: ref_post_id (FK → post.post_id), sort_order (integer, default 0)
  - Create table review_meta (post_id FK unique, media_type, subject_title, subject_creator, subject_year)
  - Create table project_meta (post_id FK unique, status, github_url)

Run from the project root:
    python migrations/add_content_types.py

The script is idempotent: it checks for each column/table before adding it
so it can be run safely against a database that already has some changes applied.
"""

import os
import sys

# Allow importing the Flask app from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import inspect, text


def column_exists(inspector, table_name, column_name):
    """Return True if the column already exists in the named table."""
    cols = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in cols


def table_exists(inspector, table_name):
    """Return True if the table exists in the current database."""
    return table_name in inspector.get_table_names()


def run():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)

        with db.engine.connect() as conn:
            # --- footnote: ref_post_id ---
            if not column_exists(inspector, 'footnote', 'ref_post_id'):
                conn.execute(text(
                    'ALTER TABLE footnote ADD COLUMN ref_post_id INTEGER REFERENCES post(post_id)'
                ))
                print('Added footnote.ref_post_id')
            else:
                print('footnote.ref_post_id already exists — skipped')

            # --- footnote: sort_order ---
            if not column_exists(inspector, 'footnote', 'sort_order'):
                conn.execute(text(
                    'ALTER TABLE footnote ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0'
                ))
                print('Added footnote.sort_order')
            else:
                print('footnote.sort_order already exists — skipped')

            # --- review_meta ---
            if not table_exists(inspector, 'review_meta'):
                conn.execute(text('''
                    CREATE TABLE review_meta (
                        review_meta_id  SERIAL PRIMARY KEY,
                        post_id         INTEGER NOT NULL UNIQUE REFERENCES post(post_id) ON DELETE CASCADE,
                        media_type      VARCHAR(20) NOT NULL DEFAULT 'other',
                        subject_title   VARCHAR(300) NOT NULL,
                        subject_creator VARCHAR(200),
                        subject_year    INTEGER
                    )
                '''))
                print('Created table review_meta')
            else:
                print('review_meta already exists — skipped')

            # --- project_meta ---
            if not table_exists(inspector, 'project_meta'):
                conn.execute(text('''
                    CREATE TABLE project_meta (
                        project_meta_id SERIAL PRIMARY KEY,
                        post_id         INTEGER NOT NULL UNIQUE REFERENCES post(post_id) ON DELETE CASCADE,
                        status          VARCHAR(20) NOT NULL DEFAULT 'in_progress',
                        github_url      VARCHAR(500)
                    )
                '''))
                print('Created table project_meta')
            else:
                print('project_meta already exists — skipped')

            conn.commit()

        print('Migration complete.')


if __name__ == '__main__':
    run()
