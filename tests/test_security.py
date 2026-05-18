"""
Security-focused tests.

Covers: admin_required blocks every admin route for anonymous users,
safe_next_url unit tests, CSRF rejection when WTF_CSRF_ENABLED is True.

No manual app.app_context() wrappers are needed — pytest-flask manages
the context.  RATELIMIT_ENABLED=False is set in the test app config so
the rate limiter does not fire before CSRF validation is reached.
"""

import pytest
from app.routes import safe_next_url


# ---------------------------------------------------------------------------
# safe_next_url unit tests (pure function, no HTTP)
# ---------------------------------------------------------------------------

class TestSafeNextUrl:
  def test_relative_path_allowed(self):
    assert safe_next_url('/admin/posts') == '/admin/posts'

  def test_root_path_allowed(self):
    assert safe_next_url('/') == '/'

  def test_none_returns_none(self):
    assert safe_next_url(None) is None

  def test_empty_string_returns_none(self):
    assert safe_next_url('') is None

  def test_absolute_http_rejected(self):
    assert safe_next_url('http://evil.example.com') is None

  def test_absolute_https_rejected(self):
    assert safe_next_url('https://evil.example.com/steal') is None

  def test_protocol_relative_rejected(self):
    assert safe_next_url('//evil.example.com') is None

  def test_path_with_query_string_allowed(self):
    assert safe_next_url('/admin/posts?page=2') == '/admin/posts?page=2'


# ---------------------------------------------------------------------------
# admin_required: every admin route must redirect anonymous users
# ---------------------------------------------------------------------------

ADMIN_GET_ROUTES = [
  '/admin',
  '/admin/posts',
  '/admin/new_post',
  '/admin/categories',
  '/admin/new_category',
  '/admin/export',
  '/admin/import',
  '/admin/2fa',
  '/admin/change_password',
]

@pytest.mark.parametrize('route', ADMIN_GET_ROUTES)
def test_admin_route_requires_login(client, route):
  """Every admin GET route redirects unauthenticated users to /login."""
  response = client.get(route, follow_redirects=False)
  assert response.status_code == 302
  assert '/login' in response.headers['Location'], \
    f'{route} did not redirect to /login for anonymous user'


# ---------------------------------------------------------------------------
# CSRF: state-changing routes reject requests without a valid token
# ---------------------------------------------------------------------------

class TestCsrf:
  def test_login_post_without_csrf_rejected(self, client, admin_user, app):
    """
    POST /login without a CSRF token is rejected with 400 when CSRF is on.

    The conftest disables CSRF globally; this test re-enables it for this
    request only and restores the original setting in a finally block.
    RATELIMIT_ENABLED=False is set globally in test config so the rate
    limiter cannot return 429 before the CSRF check fires.
    """
    app.config['WTF_CSRF_ENABLED'] = True
    try:
      response = client.post('/login', data={
        'username': 'admin',
        'password': 'correct-password',
      })
      assert response.status_code == 400
    finally:
      app.config['WTF_CSRF_ENABLED'] = False

  def test_delete_post_without_csrf_rejected(self, auth_client, sample_post, app):
    """POST /admin/delete/<id> without a CSRF token is rejected."""
    app.config['WTF_CSRF_ENABLED'] = True
    try:
      response = auth_client.post(f'/admin/delete/{sample_post}', data={})
      assert response.status_code == 400
    finally:
      app.config['WTF_CSRF_ENABLED'] = False


# ---------------------------------------------------------------------------
# admin_required: inactive user is rejected even with a valid session
# ---------------------------------------------------------------------------

class TestInactiveUser:
  def test_inactive_user_redirected_to_login(self, app, db_session):
    """
    A user with is_active=False is logged out and redirected to /login
    when accessing an admin route, even if their session is still valid.
    """
    from app.models import User
    with app.app_context():
      user = User(username='inactive', email='inactive@example.com', is_active=False)
      user.set_password('correct-password')
      db_session.add(user)
      db_session.commit()
      user_id = user.id

    with app.test_client() as c:
      # Force a session as if the user had logged in before being deactivated.
      with c.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

      response = c.get('/admin', follow_redirects=False)
      assert response.status_code == 302
      assert '/login' in response.headers['Location']
