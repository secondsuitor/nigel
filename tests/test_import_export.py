"""
Import / export round-trip tests.

Covers: JSON export structure, import creating posts and categories,
duplicate skip by wordpress_id and slug, slug collision resolution.

No manual app.app_context() wrappers are needed around test client calls.
pytest-flask manages context via the session-scoped 'app' fixture.
"""

import io
import json
import pytest

from app.models import Category, Post


def _export(auth_client):
  """Helper: hit /admin/export and return the parsed payload."""
  response = auth_client.get('/admin/export')
  assert response.status_code == 200
  return json.loads(response.data)


def _import(auth_client, payload):
  """Helper: POST a payload dict to /admin/import as a JSON file upload."""
  json_bytes = json.dumps(payload).encode()
  response = auth_client.post('/admin/import', data={
    'json_file': (io.BytesIO(json_bytes), 'posts_export.json', 'application/json'),
  }, content_type='multipart/form-data', follow_redirects=False)
  return response


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
  def test_export_returns_json(self, auth_client):
    """GET /admin/export returns application/json."""
    response = auth_client.get('/admin/export')
    assert response.status_code == 200
    assert 'application/json' in response.content_type

  def test_export_contains_required_keys(self, auth_client):
    """Exported payload has 'posts', 'categories', and 'exported_at' keys."""
    payload = _export(auth_client)
    assert 'posts' in payload
    assert 'categories' in payload
    assert 'exported_at' in payload

  def test_export_includes_published_post(self, auth_client, sample_post):
    """A published post appears in the export."""
    payload = _export(auth_client)
    titles = [p['title'] for p in payload['posts']]
    assert 'Sample Post' in titles

  def test_export_unauthenticated_redirects(self, client):
    """Unauthenticated export request redirects to login."""
    response = client.get('/admin/export', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

class TestImport:
  def _minimal_payload(self, posts=None, categories=None):
    return {
      'exported_at': '2025-01-01T00:00:00',
      'categories': categories or [],
      'posts': posts or [],
    }

  def test_import_creates_category(self, auth_client, db_session):
    """Importing a payload with a new category creates it in the DB."""
    payload = self._minimal_payload(categories=[
      {'slug': 'science', 'name': 'Science', 'description': None}
    ])
    _import(auth_client, payload)
    cat = Category.query.filter_by(slug='science').first()
    assert cat is not None
    assert cat.name == 'Science'

  def test_import_creates_post(self, auth_client, db_session):
    """Importing a payload with a new post creates it in the DB."""
    payload = self._minimal_payload(posts=[{
      'title': 'Imported Post',
      'slug': 'imported-post',
      'content': '<p>Imported</p>',
      'excerpt': None,
      'status': 'published',
      'post_type': 'post',
      'published_at': '2024-06-01T10:00:00',
      'created_at': '2024-06-01T10:00:00',
      'updated_at': '2024-06-01T10:00:00',
      'wordpress_id': None,
      'wordpress_date': None,
      'wordpress_url': None,
      'meta_description': None,
      'featured_image': None,
      'categories': [],
    }])
    _import(auth_client, payload)
    post = Post.query.filter_by(slug='imported-post').first()
    assert post is not None
    assert post.title == 'Imported Post'

  def test_import_skips_duplicate_wordpress_id(self, auth_client, db_session):
    """A post with a wordpress_id that already exists is skipped."""
    existing = Post(
      title='Existing', slug='existing', content='x',
      status='published', post_type='post', wordpress_id=42,
    )
    db_session.add(existing)
    db_session.commit()

    payload = self._minimal_payload(posts=[{
      'title': 'Duplicate WP Post',
      'slug': 'duplicate-wp-post',
      'content': '<p>Dup</p>',
      'excerpt': None,
      'status': 'published',
      'post_type': 'post',
      'published_at': None,
      'created_at': None,
      'updated_at': None,
      'wordpress_id': 42,
      'wordpress_date': None,
      'wordpress_url': None,
      'meta_description': None,
      'featured_image': None,
      'categories': [],
    }])
    _import(auth_client, payload)
    assert Post.query.filter_by(title='Duplicate WP Post').first() is None

  def test_import_resolves_slug_collision(self, auth_client, db_session):
    """
    If a slug already exists for a different post (identified by wordpress_id),
    the importer appends a counter suffix to make the slug unique.
    """
    original = Post(
      title='Original', slug='collision-slug', content='x',
      status='published', post_type='post',
    )
    db_session.add(original)
    db_session.commit()

    payload = self._minimal_payload(posts=[{
      'title': 'New Post',
      'slug': 'collision-slug',
      'content': '<p>New</p>',
      'excerpt': None,
      'status': 'published',
      'post_type': 'post',
      'published_at': None,
      'created_at': None,
      'updated_at': None,
      'wordpress_id': 999,
      'wordpress_date': None,
      'wordpress_url': None,
      'meta_description': None,
      'featured_image': None,
      'categories': [],
    }])
    _import(auth_client, payload)
    posts = Post.query.filter(Post.slug.like('collision-slug%')).all()
    slugs = {p.slug for p in posts}
    assert 'collision-slug' in slugs
    assert 'collision-slug-2' in slugs

  def test_import_invalid_json_flashes_error(self, auth_client):
    """Uploading a non-JSON file re-renders the form (200, not redirect)."""
    response = auth_client.post('/admin/import', data={
      'json_file': (io.BytesIO(b'not json at all }{'), 'bad.json', 'application/json'),
    }, content_type='multipart/form-data')
    assert response.status_code == 200
    assert b'Could not parse' in response.data
