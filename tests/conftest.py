"""
Shared pytest fixtures for the blog test suite.

All tests use a temporary SQLite file database so they are fully isolated
from the development database and from each other.  A file-based database
(rather than sqlite:///:memory:) is required because the Flask app's routes
run in their own SQLAlchemy engine connections — each new connection to an
in-memory database would see an empty schema.

The 'db_session' fixture drops and recreates all tables before each test
so no rows leak between tests.

SQLAlchemy 2.0 removed the Session.bind attribute, so the old
transaction-rollback isolation pattern no longer works.  Recreating
tables per test is the simplest correct alternative for a small suite.

The admin_user fixture creates a single User row for authentication tests
and returns its integer primary key to avoid DetachedInstanceError when
the ORM instance is accessed outside the creating session context.

The auth_client fixture returns a test client that is already logged in,
for tests that need an authenticated session without re-testing the login
flow itself.

CSRF is disabled in the test configuration so that POST tests can submit
forms without generating real tokens — the CSRF tests in test_security.py
re-enable it explicitly for the tests that check rejection behaviour.

No manual 'with app.app_context()' wrappers are needed in test functions:
pytest-flask's 'app' fixture (scope=session) manages a push context for
the session, and the test client pushes/pops its own context per request.
Adding a second manual context in the same call stack causes
"Popped wrong app context" errors in Flask 3.x.
"""

import os
import tempfile
from datetime import datetime, timezone

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret-key-not-for-production')
os.environ.setdefault('FLASK_ENV', 'development')

# Point the app at a temp SQLite file before importing create_app so the
# engine is built against the test database from the very first connection.
# This must happen before 'from app import ...' executes create_app().
_db_fd, _db_path = tempfile.mkstemp(suffix='.db')
os.close(_db_fd)
os.environ['DATABASE_URL'] = f'sqlite:///{_db_path}'

from app import create_app, db as _db, limiter, csrf
from app.models import User, Post, Category


@pytest.fixture(scope='session')
def app():
  """
  Create a Flask application configured for testing.

  The DATABASE_URL env var was set to a temp file before this module was
  imported, so create_app() builds its engine against the test database.
  CSRF, rate limiting, and secure cookies are disabled for the test context.
  """
  test_app = create_app()
  test_app.config.update({
    'TESTING': True,
    'WTF_CSRF_ENABLED': False,
    'SESSION_COOKIE_SECURE': False,
    # RATELIMIT_ENABLED is read by limiter.init_app(); we also set
    # limiter.enabled directly below because init_app() already ran.
    'RATELIMIT_ENABLED': False,
  })
  # limiter.enabled is set from config during init_app(), which already ran
  # inside create_app().  We set it directly here so the test suite is not
  # throttled by rate limits on repeated login attempts.
  limiter.enabled = False
  yield test_app
  # Clean up the temp DB file after the entire test session.
  os.unlink(_db_path)


@pytest.fixture()
def db_session(app):
  """
  Provide a clean database session for each test.

  Drops all tables and recreates them before yielding.  This is the
  correct SQLAlchemy 2.0 approach for per-test isolation with an
  in-memory SQLite database (the old session.bind trick was 1.x only).
  """
  with app.app_context():
    _db.drop_all()
    _db.create_all()
    yield _db.session
    _db.session.remove()


@pytest.fixture()
def admin_user(db_session, app):
  """
  Insert a single admin User row and return its integer primary key.

  Returning the id (not the ORM instance) prevents DetachedInstanceError
  when the instance is accessed outside the original session context.
  Tests that need the User object should call db_session.get(User, admin_user).
  """
  with app.app_context():
    user = User(username='admin', email='admin@example.com')
    user.set_password('correct-password')
    db_session.add(user)
    db_session.commit()
    return user.id


@pytest.fixture()
def client(app):
  """Unauthenticated test client."""
  return app.test_client()


@pytest.fixture()
def auth_client(app, admin_user):
  """
  Test client with an active admin session.

  Logs in via the login endpoint rather than manipulating the session
  directly, so the fixture exercises the real login path.
  No manual app.app_context() wrapper is needed: the test client pushes
  its own context for each request.
  """
  with app.test_client() as logged_in_client:
    logged_in_client.post('/login', data={
      'username': 'admin',
      'password': 'correct-password',
    }, follow_redirects=False)
    yield logged_in_client


@pytest.fixture()
def sample_post(db_session, app):
  """
  Insert a published Post row and return its integer primary key.

  Returning the id rather than the ORM instance avoids DetachedInstanceError
  when tests access the attribute outside the session context.  Tests that
  need to inspect the post should reload it with db_session.get(Post, id).
  """
  with app.app_context():
    post = Post(
      title='Sample Post',
      slug='sample-post',
      content='<p>Hello world.</p>',
      excerpt='Hello world.',
      status='published',
      post_type='post',
      published_at=datetime.now(timezone.utc),
    )
    db_session.add(post)
    db_session.commit()
    return post.id


@pytest.fixture()
def sample_category(db_session, app):
  """Insert a Category row and return its integer primary key."""
  with app.app_context():
    category = Category(name='Tech', slug='tech')
    db_session.add(category)
    db_session.commit()
    return category.category_id
