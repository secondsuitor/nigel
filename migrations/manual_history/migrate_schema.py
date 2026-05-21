#!/usr/bin/env python3
"""
Database Migration Script for Blog Schema Update
Migrates from old Nigel schema to new optimized single-user blog schema
"""

import os
import sys
import json
from datetime import datetime

# Add the parent directory to Python path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app, db
from app.models import Post, Category, Source, Footnote, User

def backup_existing_data():
    """Export existing data before migration"""
    print("Backing up existing data...")
    
    backup_data = {
        'timestamp': datetime.utcnow().isoformat(),
        'posts': [],
        'users': [],
        'sources': [],
        'footnotes': []
    }
    
    try:
        # Check if tables exist before querying
        result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        existing_tables = [row[0] for row in result.fetchall()]
        
        if 'post' in existing_tables:
            # Export posts with old schema
            old_posts = db.session.execute(text("""
                SELECT post_id, user_id, parent_id, title, content 
                FROM post
            """)).fetchall()
            
            for post in old_posts:
                backup_data['posts'].append({
                    'post_id': post[0],
                    'user_id': post[1], 
                    'parent_id': post[2],
                    'title': post[3],
                    'content': post[4]
                })
        
        if 'user' in existing_tables:
            # Export users
            old_users = db.session.execute(text("""
                SELECT user_id, username, password_hash, email 
                FROM user
            """)).fetchall()
            
            for user in old_users:
                backup_data['users'].append({
                    'user_id': user[0],
                    'username': user[1],
                    'password_hash': user[2],
                    'email': user[3]
                })
        
        if 'source' in existing_tables:
            # Export sources
            old_sources = db.session.execute(text("""
                SELECT source_id, post_id, location, page, author, title, publisher, year
                FROM source
            """)).fetchall()
            
            for source in old_sources:
                backup_data['sources'].append({
                    'source_id': source[0],
                    'post_id': source[1],
                    'location': source[2],
                    'page': source[3],
                    'author': source[4],
                    'title': source[5],
                    'publisher': source[6],
                    'year': source[7]
                })
        
        if 'footnote' in existing_tables:
            # Export footnotes
            old_footnotes = db.session.execute(text("""
                SELECT footnote_id, post_id, content, source_id
                FROM footnote
            """)).fetchall()
            
            for footnote in old_footnotes:
                backup_data['footnotes'].append({
                    'footnote_id': footnote[0],
                    'post_id': footnote[1],
                    'content': footnote[2],
                    'source_id': footnote[3]
                })
        
        # Save backup
        backup_file = f"migrations/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        print(f"Backup saved to {backup_file}")
        print(f"   - Posts: {len(backup_data['posts'])}")
        print(f"   - Users: {len(backup_data['users'])}")
        print(f"   - Sources: {len(backup_data['sources'])}")
        print(f"   - Footnotes: {len(backup_data['footnotes'])}")
        
        return backup_data
        
    except Exception as e:
        print(f"Backup failed: {e}")
        return None

def create_new_schema():
    """Create new database schema"""
    print("🔄 Creating new database schema...")
    
    try:
        # Drop all tables and recreate with new schema
        db.drop_all()
        db.create_all()
        print("New schema created successfully")
        return True
    except Exception as e:
        print(f"Schema creation failed: {e}")
        return False

def generate_slug(title):
    """Generate URL slug from title"""
    import re
    # Convert to lowercase and replace spaces with hyphens
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars
    slug = re.sub(r'[\s_-]+', '-', slug)  # Replace spaces/underscores with hyphens
    slug = slug.strip('-')  # Remove leading/trailing hyphens
    return slug[:200]  # Limit length

def migrate_data(backup_data):
    """Migrate backed up data to new schema"""
    print("Migrating data to new schema...")
    
    if not backup_data:
        print("No backup data to migrate")
        return False
    
    try:
        # Create default category
        default_category = Category(
            name='General',
            slug='general',
            description='General blog posts'
        )
        db.session.add(default_category)
        db.session.flush()  # Get the ID
        
        # Create admin user (single user blog)
        admin_user = User(
            username='admin',
            email='admin@example.com',
            is_active=True
        )
        db.session.add(admin_user)
        
        # Migrate posts
        migrated_posts = {}
        for old_post in backup_data['posts']:
            slug = generate_slug(old_post['title'])
            
            # Ensure unique slug
            existing = Post.query.filter_by(slug=slug).first()
            if existing:
                slug = f"{slug}-{old_post['post_id']}"
            
            new_post = Post(
                title=old_post['title'],
                slug=slug,
                content=old_post['content'],
                status='published',  # Assume existing posts were published
                post_type='post',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                published_at=datetime.utcnow()
            )
            
            # Add default category
            new_post.categories.append(default_category)
            
            db.session.add(new_post)
            db.session.flush()  # Get the new post ID
            
            migrated_posts[old_post['post_id']] = new_post.post_id
        
        # Migrate sources
        for old_source in backup_data['sources']:
            if old_source['post_id'] in migrated_posts:
                new_source = Source(
                    post_id=migrated_posts[old_source['post_id']],
                    author=old_source['author'],
                    title=old_source['title'],
                    publisher=old_source['publisher'],
                    year=old_source['year'],
                    page_range=str(old_source['page']) if old_source['page'] else None
                )
                db.session.add(new_source)
        
        # Migrate footnotes
        for old_footnote in backup_data['footnotes']:
            if old_footnote['post_id'] in migrated_posts:
                new_footnote = Footnote(
                    post_id=migrated_posts[old_footnote['post_id']],
                    content=old_footnote['content'],
                    source_id=old_footnote.get('source_id')  # May be None
                )
                db.session.add(new_footnote)
        
        db.session.commit()
        
        print("Data migration completed successfully")
        print(f"   - Migrated {len(backup_data['posts'])} posts")
        print(f"   - Migrated {len(backup_data['sources'])} sources")
        print(f"   - Migrated {len(backup_data['footnotes'])} footnotes")
        print(f"   - Created admin user and default category")
        
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"Data migration failed: {e}")
        return False

def main():
    """Main migration function"""
    print("Starting database migration...")
    print("=" * 50)
    
    # Initialize Flask app
    app = create_app()
    
    with app.app_context():
        # Step 1: Backup existing data
        backup_data = backup_existing_data()
        
        # Step 2: Create new schema
        if not create_new_schema():
            print("Migration failed at schema creation")
            return False
        
        # Step 3: Migrate data
        if not migrate_data(backup_data):
            print("Migration failed at data migration")
            return False
    
    print("=" * 50)
    print("Migration completed successfully!")
    print("\nNext steps:")
    print("1. Test the application with new schema")
    print("2. Run WordPress import if needed")
    print("3. Update any hardcoded references in templates")
    
    return True

if __name__ == "__main__":
    if main():
        sys.exit(0)
    else:
        sys.exit(1)