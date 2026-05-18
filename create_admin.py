#!/usr/bin/env python3
"""
Setup script to create the default admin user for the blog.
Run this after setting up the database to create the admin account.
"""

import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User

def create_admin_user():
    """Create the default admin user"""
    app = create_app()
    
    with app.app_context():
        # Check if admin user already exists
        existing_user = User.query.filter_by(username='admin').first()
        if existing_user:
            print("❌ Admin user already exists!")
            print(f"Username: {existing_user.username}")
            print(f"Email: {existing_user.email}")
            return
        
        # Create admin user
        admin = User(
            username='admin',
            email='admin@localhost'
        )
        
        # Set a default password (change this in production!)
        default_password = 'admin123'
        admin.set_password(default_password)
        
        # Add to database
        db.session.add(admin)
        db.session.commit()
        
        print("✅ Admin user created successfully!")
        print(f"Username: admin")
        print(f"Password: {default_password}")
        print(f"Email: {admin.email}")
        print("\n⚠️  IMPORTANT: Change the admin password after first login!")
        print("   You can do this by logging in and visiting the admin panel.")

if __name__ == '__main__':
    create_admin_user()