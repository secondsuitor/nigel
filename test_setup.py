#!/usr/bin/env python3
"""
Test script to verify Flask app setup and database schema
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all required modules can be imported"""
    print("🧪 Testing imports...")
    
    try:
        import flask
        print(f"Flask: {flask.__version__}")
    except ImportError as e:
        print(f"Flask import failed: {e}")
        return False
    
    try:
        import flask_sqlalchemy
        print(f"Flask-SQLAlchemy: {flask_sqlalchemy.__version__}")
    except ImportError as e:
        print(f"Flask-SQLAlchemy import failed: {e}")
        return False
    
    try:
        import flask_wtf
        print(f"Flask-WTF: {flask_wtf.__version__}")
    except ImportError as e:
        print(f"Flask-WTF import failed: {e}")
        return False
    
    try:
        import bleach
        print(f"Bleach: {bleach.__version__}")
    except ImportError as e:
        print(f"Bleach import failed: {e}")
        return False
    
    return True

def test_app_creation():
    """Test Flask app creation and database setup"""
    print("\nTesting Flask app creation...")
    
    try:
        from app import create_app
        from app import db
        app = create_app()
        
        with app.app_context():
            # Test database connection (SQLAlchemy 2.0 syntax)
            from sqlalchemy import text
            result = db.session.execute(text("SELECT 1")).fetchone()
            print("Flask app created successfully")
            print(f"Database connection established")
            print(f"  Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
            
            return app
    except Exception as e:
        print(f"App creation failed: {e}")
        return None

def test_models():
    """Test database models"""
    print("\nTesting database models...")
    
    try:
        from app.models import Post, Category, Source, Footnote, User
        print("All models imported successfully")
        
        # Check if we can create model instances
        category = Category(name="Test", slug="test")
        post = Post(title="Test Post", slug="test-post", content="Test content")
        print("Model instances created successfully")
        
        return True
    except Exception as e:
        print(f"Model test failed: {e}")
        return False

def test_routes():
    """Test route imports"""
    print("\nTesting routes...")
    
    try:
        from app import routes
        print("Routes imported successfully")
        return True
    except Exception as e:
        print(f"Routes test failed: {e}")
        return False

def test_forms():
    """Test form imports"""
    print("\nTesting forms...")
    
    try:
        from app.forms import PostForm, CategoryForm
        print("Forms imported successfully")
        return True
    except Exception as e:
        print(f"Forms test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Starting Flask application tests...")
    print("=" * 50)
    
    # Test 1: Import dependencies
    if not test_imports():
        print("\nImport tests failed. Check your virtual environment and requirements.")
        return False
    
    # Test 2: Create Flask app
    app = test_app_creation()
    if not app:
        print("\nApp creation failed. Check your configuration.")
        return False
    
    # Test 3: Database models
    if not test_models():
        print("\nModel tests failed. Check your database schema.")
        return False
    
    # Test 4: Routes
    if not test_routes():
        print("\nRoute tests failed. Check your route definitions.")
        return False
    
    # Test 5: Forms
    if not test_forms():
        print("\nForm tests failed. Check your form definitions.")
        return False
    
    print("\n" + "=" * 50)
    print("All tests passed! Your Flask application is ready.")
    print("\nNext steps:")
    print("1. Run the migration script: python migrations/migrate_schema.py")
    print("2. Import WordPress data: python import_wordpress.py")
    print("3. Start the Flask app: python wsgi.py")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)