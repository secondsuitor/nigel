"""
Post CRUD and publishing tests.

Covers: create post, edit post, publish/unpublish toggle (POST-only),
delete (POST-only), bleach sanitisation on save, unauthenticated access.

'sample_post' is the integer primary key of a pre-inserted Post row.
Tests that need to inspect the row after a request call db_session.get()
to reload it within the active session.  No manual app.app_context()
wrappers are needed — pytest-flask keeps a context live for the session.
"""

import pytest
from app.models import Post


# ---------------------------------------------------------------------------
# Public post views
# ---------------------------------------------------------------------------

class TestPublicViews:
  def test_home_shows_published_posts(self, client, sample_post):
    """Home page lists published posts."""
    response = client.get('/')
    assert response.status_code == 200
    assert b'Sample Post' in response.data

  def test_post_by_slug(self, client, sample_post):
    """Published post renders at its slug URL."""
    response = client.get('/post/sample-post')
    assert response.status_code == 200
    assert b'Sample Post' in response.data

  def test_draft_post_not_visible_publicly(self, client, db_session):
    """Draft posts return 404 on the public route."""
    draft = Post(title='Draft', slug='draft-post',
                 content='secret', status='draft', post_type='post')
    db_session.add(draft)
    db_session.commit()
    response = client.get('/post/draft-post')
    assert response.status_code == 404

  def test_nonexistent_slug_returns_404(self, client):
    """Unknown slug returns 404."""
    response = client.get('/post/does-not-exist')
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Admin post creation
# ---------------------------------------------------------------------------

class TestNewPost:
  def test_new_post_page_requires_login(self, client):
    """Unauthenticated GET /admin/new_post redirects to login."""
    response = client.get('/admin/new_post', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

  def test_new_post_page_renders(self, auth_client):
    """Authenticated GET /admin/new_post returns 200."""
    response = auth_client.get('/admin/new_post')
    assert response.status_code == 200

  def test_create_post_saves_to_db(self, auth_client, db_session):
    """POST /admin/new_post creates a draft post in the database."""
    response = auth_client.post('/admin/new_post', data={
      'title': 'My New Post',
      'content': '<p>Body text.</p>',
      'excerpt': '',
      'meta_description': '',
      'status': 'draft',
      'categories': [],
    }, follow_redirects=False)
    assert response.status_code == 302
    post = Post.query.filter_by(title='My New Post').first()
    assert post is not None
    assert post.status == 'draft'

  def test_create_post_bleach_strips_script(self, auth_client, db_session):
    """Script tags in post content are stripped by bleach on save."""
    auth_client.post('/admin/new_post', data={
      'title': 'XSS Post',
      'content': '<p>Hello</p><script>alert(1)</script>',
      'excerpt': '',
      'meta_description': '',
      'status': 'draft',
      'categories': [],
    })
    post = Post.query.filter_by(title='XSS Post').first()
    assert post is not None
    assert '<script>' not in post.content
    assert 'Hello' in post.content


# ---------------------------------------------------------------------------
# Admin post editing
# ---------------------------------------------------------------------------

class TestEditPost:
  def test_edit_post_page_renders(self, auth_client, sample_post):
    """GET /admin/edit_post/<id> returns 200."""
    response = auth_client.get(f'/admin/edit_post/{sample_post}')
    assert response.status_code == 200

  def test_edit_post_updates_title(self, auth_client, sample_post, db_session):
    """POSTing to edit_post changes the title in the database."""
    auth_client.post(f'/admin/edit_post/{sample_post}', data={
      'title': 'Updated Title',
      'content': '<p>Updated content.</p>',
      'excerpt': '',
      'meta_description': '',
      'status': 'published',
      'categories': [],
    })
    post = db_session.get(Post, sample_post)
    assert post.title == 'Updated Title'


# ---------------------------------------------------------------------------
# Publish toggle (must be POST)
# ---------------------------------------------------------------------------

class TestPublishPost:
  def test_publish_via_get_rejected(self, auth_client, sample_post):
    """GET /admin/publish/<id> is not allowed (405)."""
    response = auth_client.get(f'/admin/publish/{sample_post}')
    assert response.status_code == 405

  def test_publish_toggles_draft(self, auth_client, sample_post, db_session):
    """POST /admin/publish/<id> on a published post moves it to draft."""
    auth_client.post(f'/admin/publish/{sample_post}')
    post = db_session.get(Post, sample_post)
    assert post.status == 'draft'


# ---------------------------------------------------------------------------
# Delete (must be POST)
# ---------------------------------------------------------------------------

class TestDeletePost:
  def test_delete_via_get_rejected(self, auth_client, sample_post):
    """GET /admin/delete/<id> is not allowed (405)."""
    response = auth_client.get(f'/admin/delete/{sample_post}')
    assert response.status_code == 405

  def test_delete_removes_post(self, auth_client, sample_post, db_session):
    """POST /admin/delete/<id> removes the post from the database."""
    auth_client.post(f'/admin/delete/{sample_post}')
    assert db_session.get(Post, sample_post) is None
