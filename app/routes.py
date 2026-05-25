"""
View functions for the blog, organised under the 'main' Blueprint.

Public routes serve readers.  Admin routes are protected by the
admin_required decorator and require a valid Flask-Login session.
Image-management routes call image_utils so that the file-system logic
stays out of this module.
"""

import base64
import io
import json
import os
import re
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlsplit

import bleach
import pyotp
import qrcode
from sqlalchemy.orm import selectinload
from flask import (
  Blueprint,
  Response,
  abort,
  flash,
  redirect,
  render_template,
  request,
  session,
  url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.forms import BlueskyPostForm, CategoryForm, ChangePasswordForm, DeleteFootnoteForm, DeleteSourceForm, FootnoteForm, ImageEditForm, ImageForm, ImportForm, LoginForm, PostForm, SourceForm, TotpVerifyForm
from app.image_utils import delete_image_file, process_uploaded_image
from app.models import Category, Footnote, Image, Post, ProjectMeta, ReviewMeta, Source, User
from app import limiter
from app.atproto_utils import AtProtoAlreadyPosted, AtProtoError, build_preview, post_to_bluesky


main = Blueprint('main', __name__)

# Tags and attributes permitted in post content.
# This list is kept small on purpose: every permitted tag is a potential
# XSS vector, so additions should be deliberate and reviewed.
# img is allowed so that images uploaded via the admin can be embedded in
# post content using standard HTML; src is restricted to relative /static/
# paths by the insert helper in the editor template (not enforced here).
ALLOWED_TAGS = frozenset([
  'a', 'aside', 'b', 'blockquote', 'br', 'del', 'em',
  'figure', 'figcaption',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'i', 'img', 'li', 'ol', 'p', 'strong', 'sub', 'sup',
  'template', 'u', 'ul',
])
ALLOWED_ATTRS = {
  '*': ['class'],
  'a': ['href', 'title'],
  'img': ['src', 'alt', 'width', 'height', 'loading'],
}


def admin_required(view_function):
  """
  Decorator that redirects unauthenticated users to the login page.

  Wraps any route that should only be accessible to a logged-in admin.
  Flask-Login's login_required would also work, but this gives a
  friendlier flash message and a cleaner redirect destination.
  """
  @wraps(view_function)
  def decorated_function(*args, **kwargs):
    if not current_user.is_authenticated:
      flash('Please log in to access admin features.', 'error')
      return redirect(url_for('main.login'))
    if not current_user.is_active:
      flash('Your account is inactive.', 'error')
      logout_user()
      return redirect(url_for('main.login'))
    return view_function(*args, **kwargs)
  return decorated_function


def safe_next_url(next_url):
  """
  Return next_url only if it is a relative path on this application.

  Rejects absolute URLs (http://evil.example.com) and protocol-relative
  URLs (//evil.example.com) to prevent open-redirect attacks where an
  attacker appends ?next=https://phishing.example.com to the login URL.
  Returns None when the URL is absent or unsafe so callers fall back to
  the admin dashboard.
  """
  if not next_url:
    return None
  parsed = urlsplit(next_url)
  # An absolute URL has a scheme or a netloc; both must be absent.
  if parsed.scheme or parsed.netloc:
    return None
  return next_url


def generate_slug(title, post_id=None):
  """
  Derive a URL-safe slug from title, guaranteeing uniqueness in the Post table.

  If a conflict is found with a different post, a datestamp suffix is appended.
  The post_id argument is used during edits so that a post does not conflict
  with its own existing slug.
  """
  slug = title.lower().strip()
  slug = re.sub(r'[^\w\s-]', '', slug)
  slug = re.sub(r'[\s_-]+', '-', slug)
  slug = slug.strip('-')
  slug = slug[:200]

  existing = Post.query.filter_by(slug=slug).first()
  if existing and (not post_id or existing.id != post_id):
    # Append date so the slug stays readable.
    datestamp = datetime.now().strftime('%Y%m%d')
    slug = f'{slug}-{datestamp}'

  return slug


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@main.route('/')
def home():
  """List all published posts in reverse chronological order."""
  posts = Post.query.filter_by(status='published').order_by(Post.published_at.desc()).all()
  return render_template('home.html', title='Home', posts=posts)


@main.route('/post/<slug>')
def post(slug):
  """Render a single published post identified by its slug."""
  current_post = (
    Post.query
    .options(
      selectinload(Post.footnotes).selectinload(Footnote.source),
      selectinload(Post.footnotes).selectinload(Footnote.ref_post),
      selectinload(Post.sources),
      selectinload(Post.review_meta),
      selectinload(Post.project_meta),
      selectinload(Post.referencing_footnotes).selectinload(Footnote.post),
      selectinload(Post.categories),
    )
    .filter_by(slug=slug, status='published')
    .first_or_404()
  )
  return render_template('post.html', post=current_post)


@main.route('/post/<int:post_id>')
def post_by_id(post_id):
  """
  Redirect legacy numeric-ID URLs to the canonical slug URL.

  Preserved for backward compatibility with any old links.
  """
  found_post = db.get_or_404(Post, post_id)
  return redirect(url_for('main.post', slug=found_post.slug))


@main.route('/category/<slug>')
def category(slug):
  """List published posts belonging to the given category."""
  current_category = Category.query.filter_by(slug=slug).first_or_404()
  posts = (
    Post.query
    .filter(Post.categories.contains(current_category), Post.status == 'published')
    .order_by(Post.published_at.desc())
    .all()
  )
  return render_template('category.html', category=current_category, posts=posts)


@main.route('/feed.xml')
def rss_feed():
  """RSS 2.0 feed of the twenty most recently published posts."""
  posts = (
    Post.query
    .filter_by(status='published')
    .order_by(Post.published_at.desc())
    .limit(20)
    .all()
  )
  return (
    render_template('feed.xml', posts=posts),
    200,
    {'Content-Type': 'application/rss+xml'},
  )


@main.route('/api/posts')
def api_posts():
  """
  JSON representation of published posts for future AT Protocol integration.

  Returns a simple list; pagination and filtering can be added when needed.
  """
  posts = Post.query.filter_by(status='published').order_by(Post.published_at.desc()).all()
  return {
    'posts': [
      {
        'id': p.id,
        'title': p.title,
        'slug': p.slug,
        'excerpt': p.excerpt,
        'published_at': p.published_at.isoformat() if p.published_at else None,
        'categories': [cat.name for cat in p.categories],
      }
      for p in posts
    ]
  }


# ---------------------------------------------------------------------------
# Authentication routes
# ---------------------------------------------------------------------------

@main.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute; 30 per hour')
def login():
  """
  Display and handle the admin login form.

  If the user has 2FA enabled, a successful password check stores the user
  ID in the server-side session under the key 'pending_2fa_user_id' and
  redirects to /login/verify instead of completing the login immediately.
  This means Flask-Login is NOT called yet — the session has no active user
  until the TOTP code is also confirmed.

  If 2FA is not configured the flow is unchanged: login_user() is called
  directly and the user lands on the admin dashboard.
  """
  if current_user.is_authenticated:
    return redirect(url_for('main.admin'))

  form = LoginForm()
  if form.validate_on_submit():
    user = User.query.filter_by(username=form.username.data).first()
    if user and user.check_password(form.password.data):
      if user.has_2fa:
        # Park the user ID in the session and force a TOTP check.
        session['pending_2fa_user_id'] = user.id
        session['pending_2fa_remember'] = form.remember_me.data
        session['pending_2fa_next'] = safe_next_url(request.args.get('next'))
        return redirect(url_for('main.login_verify'))
      # No 2FA — complete login immediately.
      login_user(user, remember=form.remember_me.data)
      flash(f'Welcome back, {user.username}!', 'success')
      next_page = safe_next_url(request.args.get('next'))
      return redirect(next_page if next_page else url_for('main.admin'))
    flash('Invalid username or password.', 'error')

  return render_template('login.html', title='Login', form=form)


@main.route('/login/verify', methods=['GET', 'POST'])
@limiter.limit('10 per minute; 30 per hour')
def login_verify():
  """
  Second step of login for accounts with 2FA enabled.

  Reads the pending user ID from the server-side session set by the login
  route.  If the session key is missing the user is sent back to /login
  (e.g. if they navigate here directly).

  On a correct TOTP code, login_user() is called and the pending session
  keys are cleared.  On failure the form is re-rendered with an error; the
  session is not cleared so the user can retry without re-entering their
  password.
  """
  if current_user.is_authenticated:
    return redirect(url_for('main.admin'))

  pending_id = session.get('pending_2fa_user_id')
  if not pending_id:
    flash('Please log in first.', 'error')
    return redirect(url_for('main.login'))

  user = db.session.get(User, pending_id)
  if not user:
    session.pop('pending_2fa_user_id', None)
    flash('Session expired. Please log in again.', 'error')
    return redirect(url_for('main.login'))

  form = TotpVerifyForm()
  if form.validate_on_submit():
    totp = pyotp.TOTP(user.totp_secret)
    # valid_window=1 accepts the code from the previous and next 30-second
    # windows to accommodate minor clock drift on the user's device.
    # Replay prevention: compute the TOTP interval for the submitted code and
    # reject it if it matches the last successfully used interval.
    import time as _time
    current_interval = int(_time.time()) // 30
    if (totp.verify(form.code.data.strip(), valid_window=1)
        and current_interval != user.last_totp_at):
      user.last_totp_at = current_interval
      db.session.commit()
      remember = session.pop('pending_2fa_remember', False)
      next_page = safe_next_url(session.pop('pending_2fa_next', None))
      session.pop('pending_2fa_user_id', None)
      login_user(user, remember=remember)
      flash(f'Welcome back, {user.username}!', 'success')
      return redirect(next_page if next_page else url_for('main.admin'))
    flash('Invalid code. Please try again.', 'error')

  return render_template('login_verify.html', title='Two-Factor Authentication', form=form)


@main.route('/admin/2fa', methods=['GET', 'POST'])
@admin_required
def manage_2fa():
  """
  Show the 2FA management page.

  GET: if 2FA is not yet enabled, generate a fresh TOTP secret, store it
  in the server-side session (not in the database yet), and render the
  QR code + verification form.  If 2FA is already enabled, show a disable
  option.

  POST: validate the submitted 6-digit code against the session secret.
  On success, write the secret to the database — this is the moment 2FA
  becomes active.  The session secret is then cleared.
  """
  form = TotpVerifyForm()

  if current_user.has_2fa:
    # Already set up — nothing to do on GET; disable is handled separately.
    return render_template('admin_2fa.html', title='Two-Factor Authentication',
                           has_2fa=True, qr_data_uri=None, form=form)

  # Generate or reuse a pending secret from the session so refreshing the
  # page does not invalidate a QR code the user is in the middle of scanning.
  if 'pending_totp_secret' not in session:
    session['pending_totp_secret'] = pyotp.random_base32()

  secret = session['pending_totp_secret']
  totp = pyotp.TOTP(secret)
  provisioning_uri = totp.provisioning_uri(
    name=current_user.username,
    issuer_name='Blog Admin',
  )

  # Render the QR code as a base64 PNG so no file is written to disk.
  qr_img = qrcode.make(provisioning_uri)
  buffer = io.BytesIO()
  qr_img.save(buffer, format='PNG')
  qr_data_uri = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()

  if form.validate_on_submit():
    import time as _time
    current_interval = int(_time.time()) // 30
    if (totp.verify(form.code.data.strip(), valid_window=1)
        and current_interval != current_user.last_totp_at):
      current_user.totp_secret = secret
      current_user.last_totp_at = current_interval
      db.session.commit()
      session.pop('pending_totp_secret', None)
      flash('Two-factor authentication is now enabled.', 'success')
      return redirect(url_for('main.admin'))
    flash('Invalid code — please scan the QR code and try again.', 'error')

  return render_template('admin_2fa.html', title='Set Up Two-Factor Authentication',
                         has_2fa=False, qr_data_uri=qr_data_uri, form=form,
                         manual_key=secret)


@main.route('/admin/2fa/disable', methods=['POST'])
@admin_required
def disable_2fa():
  """
  Remove the TOTP secret for the current user, disabling 2FA.

  POST-only to prevent CSRF via a plain link.  The form in admin_2fa.html
  includes the hidden CSRF token via form.hidden_tag().
  """
  current_user.totp_secret = None
  db.session.commit()
  flash('Two-factor authentication has been disabled.', 'info')
  return redirect(url_for('main.admin'))


@main.route('/logout')
@login_required
def logout():
  """End the current session and redirect to the home page."""
  logout_user()
  flash('You have been logged out.', 'info')
  return redirect(url_for('main.home'))


@main.route('/admin/change_password', methods=['GET', 'POST'])
@admin_required
@limiter.limit('5 per minute')
def change_password():
  """
  Allow the logged-in admin to change their own password.

  The current password is verified first so that an unattended browser
  session cannot be used to silently change credentials.
  """
  form = ChangePasswordForm()
  if form.validate_on_submit():
    if not current_user.check_password(form.current_password.data):
      flash('Current password is incorrect.', 'error')
    elif form.new_password.data != form.confirm_password.data:
      flash('New passwords do not match.', 'error')
    else:
      current_user.set_password(form.new_password.data)
      db.session.commit()
      flash('Password changed successfully.', 'success')
      return redirect(url_for('main.admin'))

  return render_template('change_password.html', title='Change Password', form=form)


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

@main.route('/admin')
@admin_required
def admin():
  """Admin overview: post counts and category list."""
  published_count = Post.query.filter_by(status='published').count()
  draft_count = Post.query.filter_by(status='draft').count()
  total_posts = Post.query.count()
  categories = Category.query.all()
  return render_template(
    'admin.html',
    published_count=published_count,
    draft_count=draft_count,
    total_posts=total_posts,
    categories=categories,
  )


@main.route('/admin/posts')
@admin_required
def admin_posts():
  """List all posts regardless of status, newest first."""
  posts = Post.query.order_by(Post.created_at.desc()).all()
  return render_template('admin_posts.html', posts=posts)


# ---------------------------------------------------------------------------
# Post create/edit/publish/delete
# ---------------------------------------------------------------------------

def _save_type_meta(form, post_record):
  """
  Upsert the ReviewMeta or ProjectMeta row for a post based on form data.

  Called after the Post row is flushed so post_record.post_id is available.
  Removes an existing meta row when post_type changes away from its type,
  so stale data from a previous type does not linger.
  """
  if post_record.post_type == 'review':
    meta = post_record.review_meta
    if meta is None:
      meta = ReviewMeta(post_id=post_record.post_id)
      db.session.add(meta)
    meta.media_type = form.review_media_type.data or 'other'
    meta.subject_title = form.review_subject_title.data or ''
    meta.subject_creator = form.review_subject_creator.data or None
    meta.subject_year = form.review_subject_year.data or None
  else:
    # Post type changed away from 'review' — drop stale meta.
    if post_record.review_meta:
      db.session.delete(post_record.review_meta)

  if post_record.post_type == 'project':
    meta = post_record.project_meta
    if meta is None:
      meta = ProjectMeta(post_id=post_record.post_id)
      db.session.add(meta)
    meta.status = form.project_status.data or 'in_progress'
    meta.github_url = form.project_github_url.data or None
  else:
    if post_record.project_meta:
      db.session.delete(post_record.project_meta)


def _load_type_meta(form, post_record):
  """
  Pre-populate form fields from an existing ReviewMeta or ProjectMeta row.

  Called on GET requests in edit_post so the current values are visible.
  """
  if post_record.post_type == 'review' and post_record.review_meta:
    meta = post_record.review_meta
    form.review_media_type.data = meta.media_type
    form.review_subject_title.data = meta.subject_title
    form.review_subject_creator.data = meta.subject_creator
    form.review_subject_year.data = meta.subject_year
  if post_record.post_type == 'project' and post_record.project_meta:
    meta = post_record.project_meta
    form.project_status.data = meta.status
    form.project_github_url.data = meta.github_url


@main.route('/admin/new_post', methods=['GET', 'POST'])
@admin_required
def new_post():
  """
  Create a new post.

  Saves as draft by default so the author can review before publishing.
  On success, redirects to the edit page so images can be added immediately.
  """
  form = PostForm()
  categories = Category.query.all()

  if form.validate_on_submit():
    slug = generate_slug(form.title.data)

    new_post_record = Post(
      title=form.title.data,
      slug=slug,
      content=bleach.clean(form.content.data, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS),
      excerpt=bleach.clean(form.excerpt.data, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS) if form.excerpt.data else None,
      meta_description=form.meta_description.data or None,
      status='draft',
      post_type=form.post_type.data or 'post',
      created_at=datetime.now(timezone.utc),
      updated_at=datetime.now(timezone.utc),
    )

    db.session.add(new_post_record)
    # Flush to get the post_id before associating images or meta records.
    db.session.flush()

    _save_type_meta(form, new_post_record)

    if form.categories.data:
      selected_categories = Category.query.filter(
        Category.category_id.in_(form.categories.data)
      ).all()
      new_post_record.categories.extend(selected_categories)

    uploaded_files = request.files.getlist('images')
    for uploaded_file in uploaded_files:
      if uploaded_file and uploaded_file.filename:
        try:
          image_info = process_uploaded_image(uploaded_file, uploaded_file.filename)
          image_record = Image(
            post_id=new_post_record.id,
            filename=image_info['filename'],
            stored_filename=image_info['stored_filename'],
            file_path=image_info['file_path'],
            file_size=image_info['file_size'],
            mime_type=image_info['mime_type'],
            width=image_info['width'],
            height=image_info['height'],
            alt_text=f'Image for {new_post_record.title}',
            sort_order=len(new_post_record.images),
          )
          db.session.add(image_record)
          # The first image becomes the featured image automatically.
          if not new_post_record.featured_image:
            new_post_record.featured_image = image_record.url
            image_record.is_featured = True
          flash(f'Image "{image_info["filename"]}" uploaded.', 'success')
        except ValueError as upload_error:
          flash(f'Error uploading image: {upload_error}', 'error')

    db.session.commit()
    flash('Post created successfully.', 'success')
    return redirect(url_for('main.edit_post', post_id=new_post_record.id))

  return render_template('new_post.html', title='New Post', form=form, categories=categories)


@main.route('/admin/edit_post/<int:post_id>', methods=['GET', 'POST'])
@admin_required
def edit_post(post_id):
  """
  Edit an existing post.

  published_at is set the first time status changes to 'published' and is
  never overwritten afterwards so that the original publication date persists.
  """
  current_post = db.get_or_404(Post, post_id)
  footnotes = Footnote.query.filter_by(post_id=post_id).order_by(Footnote.sort_order).all()
  all_posts = Post.query.filter(Post.id != post_id).order_by(Post.title).all()
  categories = Category.query.all()
  form = PostForm()

  if form.validate_on_submit():
    current_post.title = form.title.data
    current_post.slug = generate_slug(form.title.data, post_id)
    current_post.content = bleach.clean(
      form.content.data, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS
    )
    current_post.excerpt = bleach.clean(form.excerpt.data, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS) if form.excerpt.data else None
    current_post.meta_description = form.meta_description.data or None
    current_post.updated_at = datetime.now(timezone.utc)

    old_status = current_post.status
    current_post.status = form.status.data
    current_post.post_type = form.post_type.data or current_post.post_type
    if old_status != 'published' and current_post.status == 'published' and not current_post.published_at:
      current_post.published_at = datetime.now(timezone.utc)

    if form.categories.data:
      current_post.categories = Category.query.filter(
        Category.category_id.in_(form.categories.data)
      ).all()
    else:
      current_post.categories = []

    _save_type_meta(form, current_post)

    db.session.commit()
    flash('Post updated successfully.', 'success')
    return redirect(url_for('main.post', slug=current_post.slug))

  elif request.method == 'GET':
    form.title.data = current_post.title
    form.content.data = current_post.content
    form.excerpt.data = current_post.excerpt
    form.meta_description.data = current_post.meta_description
    form.status.data = current_post.status
    form.post_type.data = current_post.post_type
    form.categories.data = [cat.category_id for cat in current_post.categories]
    _load_type_meta(form, current_post)

  return render_template(
    'edit_post.html',
    title='Edit Post',
    form=form,
    post=current_post,
    footnotes=footnotes,
    categories=categories,
    all_posts=all_posts,
  )


@main.route('/admin/publish/<int:post_id>', methods=['POST'])
@admin_required
def publish_post(post_id):
  """
  Toggle a post between published and draft without opening the edit form.

  POST-only to prevent CSRF via a crafted GET link or image tag.
  Sets published_at the first time a post is published.
  Redirects back to the referring page so the admin list stays in view.
  """
  current_post = db.get_or_404(Post, post_id)

  if current_post.status == 'published':
    current_post.status = 'draft'
    flash(f'"{current_post.title}" moved back to draft.', 'info')
  else:
    current_post.status = 'published'
    if not current_post.published_at:
      current_post.published_at = datetime.now(timezone.utc)
    flash(f'"{current_post.title}" published.', 'success')

  current_post.updated_at = datetime.now(timezone.utc)
  db.session.commit()
  return redirect(safe_next_url(request.referrer) or url_for('main.admin_posts'))


@main.route('/admin/delete/<int:post_id>', methods=['POST'])
@admin_required
def delete_post(post_id):
  """
  Permanently delete a post and its associated data.

  POST-only to prevent CSRF via a crafted GET link or image tag.
  Cascade rules in the Post model handle footnotes, sources, and images.
  """
  current_post = db.get_or_404(Post, post_id)
  post_title = current_post.title
  db.session.delete(current_post)
  db.session.commit()
  flash(f'Post "{post_title}" deleted.', 'info')
  return redirect(url_for('main.admin_posts'))


# ---------------------------------------------------------------------------
# Category management
# ---------------------------------------------------------------------------

@main.route('/admin/categories')
@admin_required
def admin_categories():
  """List all categories."""
  categories = Category.query.all()
  return render_template('admin_categories.html', categories=categories)


@main.route('/admin/new_category', methods=['GET', 'POST'])
@admin_required
def new_category():
  """Create a new category using the CategoryForm, which handles CSRF automatically."""
  form = CategoryForm()
  if form.validate_on_submit():
    slug = generate_slug(form.name.data)
    new_category_record = Category(name=form.name.data, slug=slug, description=form.description.data)
    db.session.add(new_category_record)
    db.session.commit()
    flash(f'Category "{form.name.data}" created.', 'success')
    return redirect(url_for('main.admin_categories'))

  return render_template('new_category.html', title='New Category', form=form)


# ---------------------------------------------------------------------------
# Image management
# ---------------------------------------------------------------------------

@main.route('/admin/post/<int:post_id>/upload_image', methods=['GET', 'POST'])
@admin_required
def upload_image(post_id):
  """
  Upload a single image with alt text, caption, and featured flag.

  If the new image is set as featured, any existing featured image for the
  post loses its featured flag so there is always at most one featured image.
  """
  current_post = db.get_or_404(Post, post_id)
  form = ImageForm()

  if form.validate_on_submit():
    try:
      image_info = process_uploaded_image(
        form.image_file.data, form.image_file.data.filename
      )

      if form.is_featured.data:
        for existing_image in current_post.images:
          existing_image.is_featured = False
        current_post.featured_image = f'/static/{image_info["file_path"]}'

      image_record = Image(
        post_id=current_post.id,
        filename=image_info['filename'],
        stored_filename=image_info['stored_filename'],
        file_path=image_info['file_path'],
        file_size=image_info['file_size'],
        mime_type=image_info['mime_type'],
        width=image_info['width'],
        height=image_info['height'],
        alt_text=form.alt_text.data or f'Image for {current_post.title}',
        caption=form.caption.data,
        is_featured=form.is_featured.data,
        sort_order=len(current_post.images),
      )

      db.session.add(image_record)
      db.session.commit()

      flash(f'Image "{image_info["filename"]}" uploaded successfully.', 'success')
      return redirect(url_for('main.edit_post', post_id=post_id))

    except ValueError as upload_error:
      flash(f'Error uploading image: {upload_error}', 'error')

  return render_template(
    'upload_image.html',
    title=f'Upload Image — {current_post.title}',
    form=form,
    post=current_post,
  )


@main.route('/admin/image/<int:image_id>/delete', methods=['POST'])
@admin_required
def delete_image(image_id):
  """
  Delete an image record and its file from disk.

  If the deleted image was the featured image, the next available image
  for the post is promoted to featured automatically.
  """
  image_record = db.get_or_404(Image, image_id)
  post_id = image_record.post_id
  parent_post = image_record.post

  delete_image_file(image_record.stored_filename)

  if image_record.is_featured:
    parent_post.featured_image = None
    replacement = (
      Image.query
      .filter(Image.post_id == post_id, Image.image_id != image_id)
      .first()
    )
    if replacement:
      parent_post.featured_image = replacement.url
      replacement.is_featured = True

  db.session.delete(image_record)
  db.session.commit()
  flash('Image deleted.', 'info')
  return redirect(url_for('main.edit_post', post_id=post_id))


@main.route('/admin/image/<int:image_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_image(image_id):
  """
  Update alt text, caption, and featured status for an existing image.

  CSRF is handled automatically by ImageEditForm (FlaskForm); no manual
  validate_csrf() call is needed here.

  Setting a new featured image clears the flag on all sibling images first.
  """
  image_record = db.get_or_404(Image, image_id)
  form = ImageEditForm()

  if form.validate_on_submit():
    image_record.alt_text = form.alt_text.data
    image_record.caption = form.caption.data

    if form.is_featured.data:
      for sibling in image_record.post.images:
        sibling.is_featured = False
      image_record.is_featured = True
      image_record.post.featured_image = image_record.url
    else:
      image_record.is_featured = False
      if image_record.post.featured_image == image_record.url:
        image_record.post.featured_image = None

    db.session.commit()
    flash('Image updated.', 'success')
    return redirect(url_for('main.edit_post', post_id=image_record.post_id))

  elif request.method == 'GET':
    form.alt_text.data = image_record.alt_text
    form.caption.data = image_record.caption
    form.is_featured.data = image_record.is_featured

  return render_template('edit_image.html', title='Edit Image', image=image_record, form=form)


# ---------------------------------------------------------------------------
# Export / import routes
# ---------------------------------------------------------------------------

@main.route('/admin/export')
@admin_required
def export_posts():
  """
  Download all posts and categories as a JSON file.

  The response is streamed with Content-Disposition: attachment so the
  browser saves it as posts_export.json rather than displaying it.
  The JSON structure mirrors what load_posts.py and /admin/import expect.
  """
  def dt_to_str(value):
    """Serialise a datetime to ISO-8601, or return None."""
    return value.strftime('%Y-%m-%dT%H:%M:%S') if value else None

  categories = db.session.execute(db.select(Category)).scalars().all()
  category_data = [
    {'slug': cat.slug, 'name': cat.name, 'description': cat.description}
    for cat in categories
  ]

  posts = db.session.execute(
    db.select(Post).order_by(Post.published_at.asc())
  ).scalars().all()
  post_data = [
    {
      'title': post.title,
      'slug': post.slug,
      'content': post.content,
      'excerpt': post.excerpt,
      'status': post.status,
      'post_type': post.post_type,
      'published_at': dt_to_str(post.published_at),
      'created_at': dt_to_str(post.created_at),
      'updated_at': dt_to_str(post.updated_at),
      'wordpress_id': post.wordpress_id,
      'wordpress_date': dt_to_str(post.wordpress_date),
      'wordpress_url': post.wordpress_url,
      'meta_description': post.meta_description,
      'featured_image': post.featured_image,
      'categories': [cat.slug for cat in post.categories],
    }
    for post in posts
  ]

  payload = {
    'exported_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
    'categories': category_data,
    'posts': post_data,
  }

  return Response(
    json.dumps(payload, ensure_ascii=False, indent=2),
    mimetype='application/json',
    headers={'Content-Disposition': 'attachment; filename="posts_export.json"'},
  )


def _validated_featured_image(value):
  """
  Return value only if it is a safe local static path, otherwise None.

  Prevents an imported JSON file from storing external URLs or path-traversal
  strings in the featured_image column.  Only paths starting with /static/
  are accepted.
  """
  if not value:
    return None
  if isinstance(value, str) and re.match(r'^/static/[\w./-]+$', value):
    return value
  return None


@main.route('/admin/import', methods=['GET', 'POST'])
@admin_required
def import_posts():
  """
  Upload a posts_export.json file and load its contents into the database.

  The file is parsed entirely in memory — nothing is saved to disk.
  Posts are matched by wordpress_id (if set) or by slug; duplicates are
  skipped.  A summary is flashed after each run.
  """
  form = ImportForm()

  if form.validate_on_submit():
    try:
      payload = json.loads(form.json_file.data.read().decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
      flash(f'Could not parse JSON file: {exc}', 'error')
      return render_template('import_posts.html', title='Import Posts', form=form)

    def parse_dt(value):
      """Parse an ISO-8601 datetime string, returning None on failure."""
      if not value:
        return None
      try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')
      except ValueError:
        return None

    # --- Categories ---
    category_map = {}
    categories_created = 0
    for cat_data in payload.get('categories', []):
      slug = cat_data['slug']
      existing = db.session.execute(
        db.select(Category).where(Category.slug == slug)
      ).scalar_one_or_none()
      if existing:
        category_map[slug] = existing
      else:
        new_cat = Category(
          slug=slug,
          name=cat_data['name'],
          description=cat_data.get('description'),
        )
        db.session.add(new_cat)
        db.session.flush()
        category_map[slug] = new_cat
        categories_created += 1

    # --- Posts ---
    existing_wp_ids = {
      row[0] for row in db.session.execute(
        db.select(Post.wordpress_id).where(Post.wordpress_id.isnot(None))
      ).all()
    }
    existing_slugs = {
      row[0] for row in db.session.execute(db.select(Post.slug)).all()
    }

    posts_loaded = 0
    posts_skipped = 0

    for post_data in payload.get('posts', []):
      wp_id = post_data.get('wordpress_id')
      if wp_id and wp_id in existing_wp_ids:
        posts_skipped += 1
        continue
      if not wp_id and post_data['slug'] in existing_slugs:
        posts_skipped += 1
        continue

      # Resolve a unique slug within this run.
      base_slug = post_data['slug']
      slug = base_slug
      counter = 2
      while slug in existing_slugs:
        slug = f'{base_slug}-{counter}'
        counter += 1
      existing_slugs.add(slug)

      post = Post(
        title=post_data['title'],
        slug=slug,
        content=bleach.clean(post_data['content'], tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS),
        excerpt=bleach.clean(post_data['excerpt'], tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS) if post_data.get('excerpt') else None,
        status=post_data['status'],
        post_type=post_data['post_type'],
        published_at=parse_dt(post_data.get('published_at')),
        created_at=parse_dt(post_data.get('created_at')) or datetime.now(timezone.utc),
        updated_at=parse_dt(post_data.get('updated_at')) or datetime.now(timezone.utc),
        wordpress_id=wp_id,
        wordpress_date=parse_dt(post_data.get('wordpress_date')),
        wordpress_url=post_data.get('wordpress_url'),
        meta_description=post_data.get('meta_description'),
        featured_image=_validated_featured_image(post_data.get('featured_image')),
      )
      for cat_slug in post_data.get('categories', []):
        if cat_slug in category_map:
          post.categories.append(category_map[cat_slug])

      db.session.add(post)
      posts_loaded += 1

    db.session.commit()

    flash(
      f'Import complete: {posts_loaded} posts loaded, '
      f'{posts_skipped} skipped, {categories_created} categories created.',
      'success',
    )
    return redirect(url_for('main.admin'))

  return render_template('import_posts.html', title='Import Posts', form=form)


# ---------------------------------------------------------------------------
# Bluesky / AT Protocol cross-posting
# ---------------------------------------------------------------------------

@main.route('/admin/bluesky/post/<int:post_id>', methods=['GET', 'POST'])
@admin_required
def bluesky_post(post_id):
  """
  Preview and confirm cross-posting a published post excerpt to Bluesky.

  GET:  Display the text that will be sent to Bluesky, derived from the
        post title and excerpt (or meta_description as fallback).  Also
        provides a custom_text field so the author can override the
        auto-generated body before posting.  If the post has already been
        sent, show the existing Bluesky record URI instead of a form.

  POST: Validate the CSRF token, call post_to_bluesky(), store the returned
        AT URI in post.bluesky_uri, and redirect back to the post list.
        On failure, re-render the preview with the error message.

  The route does not auto-post on publish; the author must visit this page
  and click confirm.  This keeps Bluesky posting deliberate and auditable.

  Credentials (BSKY_HANDLE, BSKY_APP_PASSWORD, SITE_URL) are read from
  environment variables at call time — never stored in the database.
  """
  current_post = db.get_or_404(Post, post_id)
  form = BlueskyPostForm()

  if form.validate_on_submit():
    custom_text = form.custom_text.data.strip() or None
    try:
      at_uri = post_to_bluesky(current_post, custom_text=custom_text)
      current_post.bluesky_uri = at_uri
      db.session.commit()
      flash('Post sent to Bluesky successfully.', 'success')
    except AtProtoAlreadyPosted as exc:
      flash(str(exc), 'info')
    except AtProtoError as exc:
      flash(f'Bluesky error: {exc}', 'error')
    return redirect(url_for('main.admin_posts'))

  # Build a preview of what will be sent so the author can review it.
  custom_text_override = form.custom_text.data.strip() if form.custom_text.data else None
  preview_text = build_preview(current_post, custom_text=custom_text_override)

  return render_template(
    'bluesky_post.html',
    title=f'Post to Bluesky — {current_post.title}',
    post=current_post,
    form=form,
    preview_text=preview_text,
    bsky_handle=os.environ.get('BSKY_HANDLE', ''),
  )


# ---------------------------------------------------------------------------
# Footnote CRUD
# ---------------------------------------------------------------------------

@main.route('/admin/post/<int:post_id>/footnote/add', methods=['POST'])
@admin_required
def add_footnote(post_id):
  """
  Add a new footnote to a post.

  The footnote order is set to one greater than the current maximum
  so new footnotes appear at the end of the list.  The editor toolbar
  inserts a [^N] marker in the post content using this order value.
  """
  current_post = db.get_or_404(Post, post_id)
  form = FootnoteForm(post_sources=current_post.sources)

  if form.validate_on_submit():
    max_order = db.session.execute(
      db.select(db.func.max(Footnote.sort_order)).where(Footnote.post_id == post_id)
    ).scalar() or 0

    source_id = form.source_id.data if form.source_id.data else None
    ref_post_id = form.ref_post_id.data if form.ref_post_id.data else None

    footnote = Footnote(
      post_id=post_id,
      content=bleach.clean(form.content.data, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS),
      source_id=source_id,
      ref_post_id=ref_post_id,
      sort_order=max_order + 1,
    )
    db.session.add(footnote)
    db.session.commit()
    flash('Footnote added.', 'success')
  else:
    for field_errors in form.errors.values():
      for error in field_errors:
        flash(error, 'error')

  return redirect(url_for('main.edit_post', post_id=post_id) + '#footnotes')


@main.route('/admin/footnote/<int:footnote_id>/edit', methods=['POST'])
@admin_required
def edit_footnote(footnote_id):
  """
  Update the content, source link, and cross-post reference of a footnote.

  The sort_order is not changed here; reordering is not yet implemented.
  """
  fn = db.get_or_404(Footnote, footnote_id)
  form = FootnoteForm(post_sources=fn.post.sources)

  if form.validate_on_submit():
    fn.content = bleach.clean(form.content.data, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)
    fn.source_id = form.source_id.data if form.source_id.data else None
    fn.ref_post_id = form.ref_post_id.data if form.ref_post_id.data else None
    db.session.commit()
    flash('Footnote updated.', 'success')
  else:
    for field_errors in form.errors.values():
      for error in field_errors:
        flash(error, 'error')

  return redirect(url_for('main.edit_post', post_id=fn.post_id) + '#footnotes')


@main.route('/admin/footnote/<int:footnote_id>/delete', methods=['POST'])
@admin_required
def delete_footnote(footnote_id):
  """
  Delete a footnote.

  POST-only to prevent CSRF via crafted links.  The CSRF token is validated
  by DeleteFootnoteForm which inherits from FlaskForm.
  """
  fn = db.get_or_404(Footnote, footnote_id)
  post_id = fn.post_id
  form = DeleteFootnoteForm()
  if not form.validate_on_submit():
    abort(400)
  db.session.delete(fn)
  db.session.commit()
  flash('Footnote deleted.', 'info')
  return redirect(url_for('main.edit_post', post_id=post_id) + '#footnotes')


# ---------------------------------------------------------------------------
# Source CRUD
# ---------------------------------------------------------------------------

@main.route('/admin/post/<int:post_id>/source/add', methods=['POST'])
@admin_required
def add_source(post_id):
  """
  Add a bibliographic source to a post.

  Sources can be linked to footnotes via the footnote edit form.
  """
  db.get_or_404(Post, post_id)
  form = SourceForm()

  if form.validate_on_submit():
    source = Source(
      post_id=post_id,
      author=form.author.data,
      title=form.title.data,
      publisher=form.publisher.data or None,
      year=form.year.data or None,
      url=form.url.data or None,
      isbn=form.isbn.data or None,
      page_range=form.page_range.data or None,
    )
    db.session.add(source)
    db.session.commit()
    flash('Source added.', 'success')
  else:
    for field_errors in form.errors.values():
      for error in field_errors:
        flash(error, 'error')

  return redirect(url_for('main.edit_post', post_id=post_id) + '#sources')


@main.route('/admin/source/<int:source_id>/delete', methods=['POST'])
@admin_required
def delete_source(source_id):
  """
  Delete a source record.

  Any footnotes linked to this source have their source_id set to NULL
  by the database (FK is nullable) so they are not deleted along with it.
  """
  source = db.get_or_404(Source, source_id)
  post_id = source.post_id
  form = DeleteSourceForm()
  if not form.validate_on_submit():
    abort(400)
  # Detach footnotes that reference this source before deleting.
  for fn in source.footnotes:
    fn.source_id = None
  db.session.delete(source)
  db.session.commit()
  flash('Source deleted.', 'info')
  return redirect(url_for('main.edit_post', post_id=post_id) + '#sources')


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@main.errorhandler(404)
def not_found(error):
  """Render the custom 404 page."""
  return render_template('404.html'), 404


@main.errorhandler(500)
def internal_error(error):
  """Roll back any open transaction and render the custom 500 page."""
  db.session.rollback()
  return render_template('500.html'), 500
