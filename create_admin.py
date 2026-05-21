#!/usr/bin/env python3
"""
Setup script to create the initial admin user for the blog.

Run once after setting up the production database:
  ADMIN_PASSWORD=<strong-password> python create_admin.py

The password must be supplied via the ADMIN_PASSWORD environment variable.
The script refuses to run without it so that no known default can ever
end up in a production database.
"""

import getpass
import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User


def create_admin_user():
    """
    Create the initial admin user.

    Reads the password from the ADMIN_PASSWORD environment variable.
    If the variable is not set, prompts interactively so the script is
    usable in a Gandi shell session without exposing the password in
    shell history.
    """
    password = os.environ.get('ADMIN_PASSWORD')
    if not password:
        # Interactive fallback: prompt without echoing to the terminal.
        password = getpass.getpass('Admin password: ')
    if not password:
        print('Error: ADMIN_PASSWORD must not be empty.', file=sys.stderr)
        sys.exit(1)

    app = create_app()

    with app.app_context():
        existing_user = User.query.filter_by(username='admin').first()
        if existing_user:
            print('Admin user already exists.', file=sys.stderr)
            sys.exit(1)

        admin = User(username='admin', email='admin@localhost')
        admin.set_password(password)

        db.session.add(admin)
        db.session.commit()

        print('Admin user created successfully.')
        print('Set up TOTP 2FA immediately after first login.')


if __name__ == '__main__':
    create_admin_user()
