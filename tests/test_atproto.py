"""
AT Protocol / Bluesky utility tests.

Tests the pure functions in atproto_utils.py — no network calls are made.
post_to_bluesky() is tested only for its guard conditions (missing credentials,
already-posted); the actual API call is mocked.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.atproto_utils import (
  AtProtoAlreadyPosted,
  AtProtoError,
  build_preview,
  post_to_bluesky,
)
from app.models import Post


def _make_post(**kwargs):
  """Return an unsaved Post instance with sensible defaults."""
  defaults = dict(
    title='My Essay Title',
    slug='my-essay-title',
    content='<p>Body</p>',
    excerpt='A short excerpt about the topic.',
    status='published',
    post_type='post',
    bluesky_uri=None,
  )
  defaults.update(kwargs)
  post = Post(**defaults)
  return post


# ---------------------------------------------------------------------------
# build_preview
# ---------------------------------------------------------------------------

class TestBuildPreview:
  def test_contains_title(self):
    post = _make_post()
    text = build_preview(post)
    assert 'My Essay Title' in text

  def test_contains_excerpt(self):
    post = _make_post()
    text = build_preview(post)
    assert 'A short excerpt' in text

  def test_contains_slug_url(self, monkeypatch):
    monkeypatch.setenv('SITE_URL', 'https://example.com')
    post = _make_post()
    text = build_preview(post)
    assert 'https://example.com/post/my-essay-title' in text

  def test_custom_text_replaces_body(self, monkeypatch):
    monkeypatch.setenv('SITE_URL', 'https://example.com')
    post = _make_post()
    text = build_preview(post, custom_text='My custom announcement')
    assert 'My custom announcement' in text
    assert 'My Essay Title' not in text

  def test_long_text_truncated_to_fit(self):
    long_excerpt = 'word ' * 200
    post = _make_post(excerpt=long_excerpt)
    text = build_preview(post)
    # Total graphemes must stay within Bluesky's 300 limit.
    assert len(text) <= 300

  def test_url_always_on_last_line(self, monkeypatch):
    monkeypatch.setenv('SITE_URL', 'https://example.com')
    post = _make_post()
    text = build_preview(post)
    last_line = text.strip().split('\n')[-1]
    assert last_line.startswith('https://example.com/post/')

  def test_falls_back_to_meta_description_when_no_excerpt(self, monkeypatch):
    monkeypatch.setenv('SITE_URL', 'https://example.com')
    post = _make_post(excerpt=None, meta_description='Meta fallback text')
    text = build_preview(post)
    assert 'Meta fallback text' in text

  def test_works_with_no_excerpt_or_meta(self, monkeypatch):
    monkeypatch.setenv('SITE_URL', 'https://example.com')
    post = _make_post(excerpt=None, meta_description=None)
    text = build_preview(post)
    assert 'My Essay Title' in text
    assert len(text) <= 300


# ---------------------------------------------------------------------------
# post_to_bluesky guard conditions (no network)
# ---------------------------------------------------------------------------

class TestPostToBlueskyGuards:
  def test_raises_already_posted_when_uri_set(self):
    """Already-posted guard fires before any credential check."""
    post = _make_post(bluesky_uri='at://did:plc:abc/app.bsky.feed.post/xyz')
    with pytest.raises(AtProtoAlreadyPosted):
      post_to_bluesky(post)

  def test_raises_error_when_handle_missing(self, monkeypatch):
    """Missing BSKY_HANDLE raises AtProtoError."""
    monkeypatch.delenv('BSKY_HANDLE', raising=False)
    monkeypatch.setenv('BSKY_APP_PASSWORD', 'app-password')
    post = _make_post()
    with pytest.raises(AtProtoError, match='BSKY_HANDLE'):
      post_to_bluesky(post)

  def test_raises_error_when_password_missing(self, monkeypatch):
    """Missing BSKY_APP_PASSWORD raises AtProtoError."""
    monkeypatch.setenv('BSKY_HANDLE', 'me.bsky.social')
    monkeypatch.delenv('BSKY_APP_PASSWORD', raising=False)
    post = _make_post()
    with pytest.raises(AtProtoError, match='BSKY_APP_PASSWORD'):
      post_to_bluesky(post)

  def test_successful_post_returns_uri(self, monkeypatch):
    """
    When credentials are present and the API succeeds, the AT URI is returned.

    The atproto Client is mocked so no real network call is made.
    """
    monkeypatch.setenv('BSKY_HANDLE', 'me.bsky.social')
    monkeypatch.setenv('BSKY_APP_PASSWORD', 'xxxx-xxxx-xxxx-xxxx')
    monkeypatch.setenv('SITE_URL', 'https://example.com')

    fake_response = MagicMock()
    fake_response.uri = 'at://did:plc:abc/app.bsky.feed.post/xyz'

    with patch('app.atproto_utils.Client') as MockClient:
      instance = MockClient.return_value
      instance.send_post.return_value = fake_response

      post = _make_post()
      result = post_to_bluesky(post)

    assert result == 'at://did:plc:abc/app.bsky.feed.post/xyz'

  def test_api_exception_wrapped_as_atproto_error(self, monkeypatch):
    """Network errors from the atproto SDK are wrapped in AtProtoError."""
    monkeypatch.setenv('BSKY_HANDLE', 'me.bsky.social')
    monkeypatch.setenv('BSKY_APP_PASSWORD', 'xxxx-xxxx-xxxx-xxxx')
    monkeypatch.setenv('SITE_URL', 'https://example.com')

    with patch('app.atproto_utils.Client') as MockClient:
      instance = MockClient.return_value
      instance.send_post.side_effect = RuntimeError('connection refused')

      post = _make_post()
      with pytest.raises(AtProtoError, match='check server logs'):
        post_to_bluesky(post)
