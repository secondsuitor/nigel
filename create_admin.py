#!/usr/bin/env python3
"""
First-deploy bootstrap script.

Run once after deploying to production:
  ADMIN_PASSWORD=<strong-password> python create_admin.py

What it does (all steps are idempotent — safe to re-run):
  1. Creates all database tables if they do not already exist.
  2. Creates the admin user if no user named 'admin' exists yet.

The password must be supplied via the ADMIN_PASSWORD environment variable.
If the variable is not set the script prompts interactively so that the
password is never visible in shell history.
"""

import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User


def bootstrap():
    """
    Initialise the database schema and create the admin user.

    Steps that are already complete are skipped without error so this
    script can be re-run safely on subsequent deploys.
    """
    password = os.environ.get('ADMIN_PASSWORD')
    if not password:
        password = getpass.getpass('Admin password: ')
    if not password:
        print('Error: ADMIN_PASSWORD must not be empty.', file=sys.stderr)
        sys.exit(1)

    app = create_app()

    with app.app_context():
        # Step 1: create tables that do not yet exist.
        # db.create_all() is a no-op for tables that are already present,
        # so existing data is never touched.
        db.create_all()
        print('Database schema: OK')

        # Step 2: create the admin user if it does not already exist.
        if User.query.filter_by(username='admin').first():
            print('Admin user: already exists, skipping.')
            return

        admin = User(username='admin', email='admin@localhost')
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print('Admin user: created.')
        print('Next step: log in and set up TOTP 2FA immediately.')


if __name__ == '__main__':
    bootstrap()
