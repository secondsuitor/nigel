"""
AT Protocol / Bluesky cross-posting utilities.

All external network calls are isolated in this module so the rest of the
app has no direct dependency on the atproto SDK.  Callers catch the two
exceptions defined here and surface them to the user via flash messages.

Required environment variables
-------------------------------
BSKY_HANDLE       Your Bluesky handle, e.g. you.bsky.social or your custom domain
BSKY_APP_PASSWORD An app password created at Settings → Privacy & Security → App passwords
SITE_URL          Canonical origin used to build the post link, e.g. https://yoursite.com
                  Defaults to '' (relative URL) if not set — fine for local testing.

The module intentionally does NOT read from a config file so that credentials
are never accidentally committed to the repository.
"""

import os
import textwrap

from atproto import Client
from atproto_client.models.app.bsky.richtext.facet import (
  Main as Facet,
  ByteSlice,
  Link,
)

# Bluesky enforces a 300 grapheme limit on post text.
# We reserve a few chars for the newline before the URL and a small buffer.
_TEXT_BODY_LIMIT = 260
_URL_PLACEHOLDER = 'https://placeholder.invalid/post'  # used to measure byte offsets


class AtProtoError(Exception):
  """Raised when credentials are missing or the atproto API call fails."""


class AtProtoAlreadyPosted(Exception):
  """Raised when the post already has a recorded Bluesky URI."""


def _build_post_text(post, custom_text=None):
  """
  Compose the Bluesky post text from a Post record.

  The text is constructed as:
    <title or custom_text>
    <excerpt, truncated to fit the 300 grapheme limit>
    <blank line>
    <canonical URL>

  If custom_text is provided it replaces the title + excerpt entirely and
  is itself truncated.  The URL is always appended on a new line and is
  represented as a link facet (rich text) in the AT Protocol record.

  Returns (text, url) so the caller can build the facet from the URL's
  byte position in the encoded text.
  """
  site_url = os.environ.get('SITE_URL', '').rstrip('/')
  post_url = f'{site_url}/post/{post.slug}'

  if custom_text:
    body = custom_text.strip()
  else:
    title = post.title.strip()
    excerpt = (post.excerpt or post.meta_description or '').strip()

    # Build body as "title\nexcerpt", then trim if needed to leave room for
    # the URL line (\n<url>) and a small safety margin.
    if excerpt:
      candidate = f'{title}\n{excerpt}'
    else:
      candidate = title

    # textwrap.shorten works on words so it won't cut mid-word.
    body = textwrap.shorten(candidate, width=_TEXT_BODY_LIMIT, placeholder='…')

  text = f'{body}\n\n{post_url}'
  return text, post_url


def build_preview(post, custom_text=None):
  """
  Return the text string that would be sent to Bluesky, without authenticating.

  Useful for rendering a confirmation page before the user commits to posting.
  """
  text, _url = _build_post_text(post, custom_text)
  return text


def post_to_bluesky(post, custom_text=None):
  """
  Publish a post excerpt to Bluesky and return the resulting AT URI.

  The canonical post URL is embedded as a rich-text link facet pointing at
  the last segment of the post text so it renders as a clickable hyperlink
  in Bluesky clients.

  Parameters
  ----------
  post        : Post model instance.  Must have .title, .slug, .excerpt.
  custom_text : Optional override for the post body.  When supplied, the
                title and excerpt are ignored and this text is used instead
                (still truncated to fit the 300-char limit).

  Returns
  -------
  str  The at:// URI of the newly created record, e.g.
       at://did:plc:xxx/app.bsky.feed.post/yyy
       Store this in post.bluesky_uri so the post is not cross-posted twice.

  Raises
  ------
  AtProtoError          Credentials missing, network failure, or API error.
  AtProtoAlreadyPosted  post.bluesky_uri is already set.
  """
  if post.bluesky_uri:
    raise AtProtoAlreadyPosted(
      f'This post was already sent to Bluesky: {post.bluesky_uri}'
    )

  handle = os.environ.get('BSKY_HANDLE', '').strip()
  app_password = os.environ.get('BSKY_APP_PASSWORD', '').strip()

  if not handle or not app_password:
    raise AtProtoError(
      'BSKY_HANDLE and BSKY_APP_PASSWORD environment variables must be set '
      'before cross-posting to Bluesky.'
    )

  text, post_url = _build_post_text(post, custom_text)

  # Build a byte-slice link facet so the URL renders as a hyperlink.
  # AT Protocol facets reference byte offsets in the UTF-8-encoded text,
  # not character positions, so we encode before measuring.
  encoded = text.encode('utf-8')
  url_bytes = post_url.encode('utf-8')
  url_start = encoded.rfind(url_bytes)

  if url_start == -1:
    # Fallback: post without a facet rather than crashing.
    facets = None
  else:
    url_end = url_start + len(url_bytes)
    facets = [
      Facet(
        index=ByteSlice(byte_start=url_start, byte_end=url_end),
        features=[Link(uri=post_url)],
      )
    ]

  try:
    client = Client()
    client.login(handle, app_password)
    response = client.send_post(text=text, facets=facets)
  except Exception as exc:
    raise AtProtoError(f'Bluesky API error: {exc}') from exc

  # response.uri is the at:// URI of the new record.
  return response.uri
