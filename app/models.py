import os
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


# Junction table for the many-to-many relationship between posts and categories.
# Defined at module level so SQLAlchemy registers it before the models.
post_categories = db.Table(
  'post_categories',
  db.Column('post_id', db.Integer, db.ForeignKey('post.post_id'), primary_key=True),
  db.Column('category_id', db.Integer, db.ForeignKey('category.category_id'), primary_key=True),
)


class Post(db.Model):
  """
  A single piece of writing: blog post, essay, analysis, or resume entry.

  The wordpress_* fields are populated during the one-time import from the
  secondsuitor backup and should not be modified afterwards.  published_at
  is set from wordpress_date on import so URLs and RSS dates are accurate.
  """
  id = db.Column('post_id', db.Integer, primary_key=True)
  title = db.Column(db.String(200), nullable=False)
  slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
  content = db.Column(db.Text, nullable=False)
  excerpt = db.Column(db.Text, nullable=True)

  # Controls visibility: draft / published / archived
  status = db.Column(db.String(20), default='draft')
  # Allows filtering by writing type: post / essay / analysis / resume
  post_type = db.Column(db.String(50), default='post')

  # created_at records when the row was first written to this database.
  # published_at is the canonical public date shown to readers.
  # wordpress_date preserves the original publication date from the import.
  created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
  updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
  published_at = db.Column(db.DateTime, nullable=True)
  wordpress_date = db.Column(db.DateTime, nullable=True)

  # Source tracking from the WordPress import — read-only after import.
  wordpress_id = db.Column(db.Integer, nullable=True, unique=True)
  wordpress_url = db.Column(db.String(500), nullable=True)

  # SEO fields.  meta_description is also used for AT Protocol cross-posting.
  meta_description = db.Column(db.String(300), nullable=True)
  # Stores the URL path to the featured image, e.g. /static/uploads/<uuid>.jpg
  featured_image = db.Column(db.String(500), nullable=True)
  # AT Protocol URI returned by Bluesky after a successful cross-post.
  # Format: at://did:plc:<id>/app.bsky.feed.post/<rkey>
  # None means the post has not been sent to Bluesky yet.
  # Never overwrite an existing URI — use it to link back to the Bluesky record.
  bluesky_uri = db.Column(db.String(200), nullable=True)

  categories = db.relationship('Category', secondary=post_categories, backref='posts')
  sources = db.relationship('Source', backref='post', cascade='all, delete-orphan')
  footnotes = db.relationship(
    'Footnote',
    foreign_keys='Footnote.post_id',
    backref='post',
    cascade='all, delete-orphan',
    order_by='Footnote.sort_order',
  )
  images = db.relationship('Image', backref='post', cascade='all, delete-orphan', order_by='Image.sort_order')

  def __repr__(self):
    return f'<Post {self.id}: {self.title!r}>'


class Image(db.Model):
  """
  An image file uploaded and associated with a post.

  Files are stored in app/static/uploads/ using a UUID-based filename to
  prevent collisions and avoid exposing original filenames in URLs.
  The url property returns the path ready to use in a src attribute.
  """
  image_id = db.Column(db.Integer, primary_key=True)
  post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=False)

  # Original name supplied by the uploader — kept for display only.
  filename = db.Column(db.String(255), nullable=False)
  # UUID-based name used on disk and in URLs.
  stored_filename = db.Column(db.String(255), nullable=False)
  # Relative path from the static folder, e.g. uploads/<uuid>.jpg
  file_path = db.Column(db.String(500), nullable=False)
  file_size = db.Column(db.Integer, nullable=False)
  mime_type = db.Column(db.String(50), nullable=False)

  width = db.Column(db.Integer, nullable=True)
  height = db.Column(db.Integer, nullable=True)

  # alt_text is required for accessibility and should describe the image content.
  alt_text = db.Column(db.String(300), nullable=True)
  caption = db.Column(db.Text, nullable=True)
  # Lower sort_order values appear first.
  sort_order = db.Column(db.Integer, default=0)
  # Only one image per post should have is_featured=True.
  is_featured = db.Column(db.Boolean, default=False)

  uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

  def __repr__(self):
    return f'<Image {self.image_id}: {self.filename!r}>'

  @property
  def url(self):
    """URL path for use in HTML src attributes."""
    return f'/static/uploads/{self.stored_filename}'

  @property
  def full_path(self):
    """Absolute filesystem path to the stored file."""
    return os.path.join('app', 'static', 'uploads', self.stored_filename)


class Category(db.Model):
  """
  A label used to group posts by topic.

  Slugs are generated from the name at creation time and should not change
  afterwards because they are part of public URLs.
  """
  category_id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(100), unique=True, nullable=False)
  slug = db.Column(db.String(100), unique=True, nullable=False)
  description = db.Column(db.Text, nullable=True)

  def __repr__(self):
    return f'<Category {self.category_id}: {self.name!r}>'


class User(UserMixin, db.Model):
  """
  The single administrator account for this blog.

  Passwords are never stored in plain text.  Use set_password() when creating
  or changing a password.  Flask-Login uses get_id() to identify sessions.
  """
  id = db.Column('user_id', db.Integer, primary_key=True)
  username = db.Column(db.String(100), unique=True, nullable=False)
  email = db.Column(db.String(200), nullable=False)
  password_hash = db.Column(db.String(255), nullable=False)
  is_active = db.Column(db.Boolean, default=True)

  # Stores the base32 TOTP secret when 2FA is enabled; None means disabled.
  # Never expose this value in logs, exports, or API responses.
  totp_secret = db.Column(db.String(64), nullable=True)

  def set_password(self, password):
    """Hash and store a new password.  Call db.session.commit() afterwards."""
    self.password_hash = generate_password_hash(password)

  def check_password(self, password):
    """Return True if the given plain-text password matches the stored hash."""
    return check_password_hash(self.password_hash, password)

  @property
  def has_2fa(self):
    """Return True when a TOTP secret is configured for this account."""
    return bool(self.totp_secret)

  def get_id(self):
    """Return the user's primary key as a string, as required by Flask-Login."""
    return str(self.id)

  def __repr__(self):
    return f'<User {self.id}: {self.username!r}>'


class Source(db.Model):
  """
  A bibliographic reference cited within a post.

  page_range accepts either a single page ("23") or a range ("23-45").
  """
  source_id = db.Column(db.Integer, primary_key=True)
  post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=False)
  author = db.Column(db.String(200), nullable=False)
  title = db.Column(db.String(300), nullable=False)
  publisher = db.Column(db.String(200), nullable=True)
  year = db.Column(db.Integer, nullable=True)
  url = db.Column(db.String(500), nullable=True)
  isbn = db.Column(db.String(50), nullable=True)
  page_range = db.Column(db.String(20), nullable=True)

  def __repr__(self):
    return f'<Source {self.source_id}: {self.title!r}>'


class Footnote(db.Model):
  """
  An inline footnote attached to a post, optionally linked to a Source.

  anchor_text is the word or phrase in the post content that the footnote
  annotates.  It is used to build back-links in the rendered HTML.
  """
  footnote_id = db.Column(db.Integer, primary_key=True)
  post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=False)
  content = db.Column(db.Text, nullable=False)
  source_id = db.Column(db.Integer, db.ForeignKey('source.source_id'), nullable=True)
  anchor_text = db.Column(db.String(100), nullable=True)
  # When set, this footnote acts as a cross-post reference pointing to another
  # post on the blog.  Displayed as "see also: <post title>" alongside or
  # instead of a bibliographic source.
  ref_post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=True)
  # Controls the display order within a post's footnote list.
  sort_order = db.Column(db.Integer, default=0, nullable=False)

  source = db.relationship('Source', backref='footnotes')
  # Use foreign_keys to disambiguate from the post_id FK on the same table.
  ref_post = db.relationship('Post', foreign_keys=[ref_post_id], backref='referencing_footnotes')

  def __repr__(self):
    return f'<Footnote {self.footnote_id}>'


class ReviewMeta(db.Model):
  """
  Extra metadata for posts of type 'review'.

  One ReviewMeta row per post.  subject_creator and subject_year are
  optional because not all media types have a single named creator or a
  clear publication year.
  """
  review_meta_id = db.Column(db.Integer, primary_key=True)
  post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=False, unique=True)
  # Broad media category shown in the post header.
  # Valid values: book, film, tv, music, game, article, other
  media_type = db.Column(db.String(20), nullable=False, default='other')
  # Title of the thing being reviewed (not the post title).
  subject_title = db.Column(db.String(300), nullable=False)
  # Author, director, artist, etc.  Nullable for group works or unknown origin.
  subject_creator = db.Column(db.String(200), nullable=True)
  # Year of original release/publication.
  subject_year = db.Column(db.Integer, nullable=True)

  post = db.relationship('Post', backref=db.backref('review_meta', uselist=False))

  def __repr__(self):
    return f'<ReviewMeta {self.review_meta_id}: {self.subject_title!r}>'


class ProjectMeta(db.Model):
  """
  Extra metadata for posts of type 'project'.

  One ProjectMeta row per post.
  """
  project_meta_id = db.Column(db.Integer, primary_key=True)
  post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=False, unique=True)
  # Workflow state of the project.
  # Valid values: in_progress, completed, abandoned
  status = db.Column(db.String(20), nullable=False, default='in_progress')
  github_url = db.Column(db.String(500), nullable=True)

  post = db.relationship('Post', backref=db.backref('project_meta', uselist=False))

  def __repr__(self):
    return f'<ProjectMeta {self.project_meta_id}: status={self.status!r}>'

