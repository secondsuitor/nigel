"""
Authentication tests.

Covers: login success/failure, 2FA pending session, next-parameter redirect
validation, unauthenticated access, logout.

No 'with app.app_context()' wrappers are needed around test client calls:
pytest-flask's 'app' fixture (scope=session) keeps a push context alive
for the whole session, and the test client pushes/pops its own context
per request.  Adding a second manual context causes "Popped wrong app
context" errors in Flask 3.x.
"""

import pyotp
import pytest

from app.models import User


# ---------------------------------------------------------------------------
# Login — basic
# ---------------------------------------------------------------------------

class TestLogin:
  def test_login_page_renders(self, client):
    """GET /login returns 200."""
    response = client.get('/login')
    assert response.status_code == 200

  def test_login_success_redirects_to_admin(self, client, admin_user):
    """Correct credentials redirect to /admin."""
    response = client.post('/login', data={
      'username': 'admin',
      'password': 'correct-password',
    }, follow_redirects=False)
    assert response.status_code == 302
    assert '/admin' in response.headers['Location']

  def test_login_wrong_password(self, client, admin_user):
    """Wrong password re-renders login with 200 (no redirect)."""
    response = client.post('/login', data={
      'username': 'admin',
      'password': 'wrong-password',
    }, follow_redirects=False)
    assert response.status_code == 200
    assert b'Invalid username or password' in response.data

  def test_login_unknown_username(self, client):
    """Unknown username re-renders login with 200."""
    response = client.post('/login', data={
      'username': 'nobody',
      'password': 'anything',
    }, follow_redirects=False)
    assert response.status_code == 200
    assert b'Invalid username or password' in response.data

  def test_already_authenticated_redirects(self, auth_client):
    """Visiting /login while already logged in redirects to /admin."""
    response = auth_client.get('/login', follow_redirects=False)
    assert response.status_code == 302
    assert '/admin' in response.headers['Location']


# ---------------------------------------------------------------------------
# Login — next parameter (open redirect prevention)
# ---------------------------------------------------------------------------

class TestNextRedirect:
  def test_safe_relative_next_is_followed(self, client, admin_user):
    """A safe relative next= URL is used after login."""
    response = client.post('/login?next=/admin/posts', data={
      'username': 'admin',
      'password': 'correct-password',
    }, follow_redirects=False)
    assert response.status_code == 302
    assert '/admin/posts' in response.headers['Location']

  def test_absolute_next_url_is_rejected(self, client, admin_user):
    """An absolute next= URL is ignored; user lands on /admin instead."""
    response = client.post('/login?next=https://evil.example.com', data={
      'username': 'admin',
      'password': 'correct-password',
    }, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers['Location']
    assert 'evil.example.com' not in location
    assert '/admin' in location

  def test_protocol_relative_next_url_is_rejected(self, client, admin_user):
    """A protocol-relative next= URL (//evil.com) is ignored."""
    response = client.post('/login?next=//evil.example.com', data={
      'username': 'admin',
      'password': 'correct-password',
    }, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers['Location']
    assert 'evil.example.com' not in location


# ---------------------------------------------------------------------------
# Login — 2FA flow
# ---------------------------------------------------------------------------

class TestTwoFactor:
  def _enable_2fa(self, admin_user_id, db_session):
    """
    Set a TOTP secret on the admin user and commit.

    We reload by id because 'admin_user' is now a plain int (the fixture
    returns the primary key to avoid DetachedInstanceError).
    """
    secret = pyotp.random_base32()
    user = db_session.get(User, admin_user_id)
    user.totp_secret = secret
    db_session.commit()
    return secret

  def test_2fa_pending_session_set_after_password(
      self, client, admin_user, db_session, app):
    """After correct password when 2FA is on, session holds pending_2fa_user_id."""
    self._enable_2fa(admin_user, db_session)

    with client.session_transaction() as pre:
      assert 'pending_2fa_user_id' not in pre

    client.post('/login', data={
      'username': 'admin',
      'password': 'correct-password',
    })

    with client.session_transaction() as post:
      assert 'pending_2fa_user_id' in post

  def test_2fa_verify_correct_code_logs_in(
      self, client, admin_user, db_session):
    """Correct TOTP code at /login/verify completes login."""
    secret = self._enable_2fa(admin_user, db_session)
    client.post('/login', data={
      'username': 'admin',
      'password': 'correct-password',
    })
    code = pyotp.TOTP(secret).now()
    response = client.post('/login/verify', data={'code': code},
                           follow_redirects=False)
    assert response.status_code == 302
    assert '/admin' in response.headers['Location']

  def test_2fa_verify_wrong_code_rejected(
      self, client, admin_user, db_session):
    """Wrong TOTP code re-renders the verify page."""
    self._enable_2fa(admin_user, db_session)
    client.post('/login', data={
      'username': 'admin',
      'password': 'correct-password',
    })
    response = client.post('/login/verify', data={'code': '000000'},
                           follow_redirects=False)
    assert response.status_code == 200
    assert b'Invalid code' in response.data

  def test_2fa_verify_without_pending_session_redirects(self, client):
    """Visiting /login/verify without a pending session redirects to /login."""
    response = client.get('/login/verify', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

  def test_2fa_code_cannot_be_replayed(self, client, admin_user, db_session, app):
    """
    A TOTP code that has already been used must be rejected on the second
    submission within the same 30-second window (replay attack prevention).

    After the first successful login the user.last_totp_at is set to the
    current time, which pyotp passes as the last_otp argument to verify().
    The same code submitted again must fail.
    """
    secret = self._enable_2fa(admin_user, db_session)

    # First login — succeeds and sets last_totp_at.
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    code = pyotp.TOTP(secret).now()
    response = client.post('/login/verify', data={'code': code}, follow_redirects=False)
    assert response.status_code == 302

    # Log out so we can attempt a second verification.
    client.get('/logout')

    # Start a fresh pending session with the same (now replayed) code.
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    response = client.post('/login/verify', data={'code': code}, follow_redirects=False)
    # pyotp.verify() returns False when last_otp matches — the route re-renders
    # the verify page (200) with an error message.
    assert response.status_code == 200
    assert b'Invalid code' in response.data


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:
  def test_logout_redirects_to_home(self, auth_client):
    """Logout redirects to home."""
    response = auth_client.get('/logout', follow_redirects=False)
    assert response.status_code == 302
    assert '/' in response.headers['Location']

  def test_logout_ends_session(self, auth_client):
    """After logout, /admin redirects to login."""
    auth_client.get('/logout')
    response = auth_client.get('/admin', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
