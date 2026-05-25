"""
WTForms form classes for the blog.

Each form is CSRF-protected via Flask-WTF.  PostForm and ImageForm handle
file uploads; the image validators enforce allowed extensions but do not
check file size (that is done in image_utils.process_uploaded_image).
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
  BooleanField,
  IntegerField,
  PasswordField,
  SelectField,
  SelectMultipleField,
  StringField,
  SubmitField,
  TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp, URL

from app.models import Category, Post


class LoginForm(FlaskForm):
  """Admin login form.  Submitted credentials are checked against the User table."""
  username = StringField('Username', validators=[DataRequired()])
  password = PasswordField('Password', validators=[DataRequired()])
  remember_me = BooleanField('Remember Me')
  submit = SubmitField('Sign In')


class PostForm(FlaskForm):
  """
  Combined form for creating and editing a post, including optional image uploads.

  Category choices are populated dynamically in __init__ so new categories
  created after app startup are visible without a restart.
  """
  title = TextAreaField(
    'Title',
    validators=[DataRequired(), Length(min=1, max=200)],
    render_kw={'rows': 1, 'cols': 80},
  )
  content = TextAreaField(
    'Content',
    validators=[DataRequired()],
    render_kw={'rows': 25, 'cols': 80},
  )
  excerpt = TextAreaField(
    'Excerpt',
    validators=[Optional(), Length(max=500)],
    render_kw={'placeholder': 'Brief description of the post (optional)'},
  )
  meta_description = StringField(
    'Meta Description',
    validators=[Optional(), Length(max=300)],
    render_kw={'placeholder': 'SEO meta description (optional)'},
  )
  status = SelectField(
    'Status',
    choices=[('draft', 'Draft'), ('published', 'Published'), ('archived', 'Archived')],
    default='draft',
  )
  post_type = SelectField(
    'Post Type',
    choices=[
      ('post', 'Post'),
      ('essay', 'Essay'),
      ('analysis', 'Analysis'),
      ('resume', 'Resume'),
      ('review', 'Review'),
      ('project', 'Project'),
    ],
    default='post',
  )
  categories = SelectMultipleField('Categories', coerce=int, validators=[Optional()])

  # Review-specific fields — only used when post_type == 'review'.
  review_media_type = SelectField(
    'Media Type',
    choices=[
      ('book', 'Book'), ('film', 'Film'), ('tv', 'TV'), ('music', 'Music'),
      ('game', 'Game'), ('article', 'Article'), ('other', 'Other'),
    ],
    default='other',
  )
  review_subject_title = StringField(
    'Subject Title',
    validators=[Optional(), Length(max=300)],
    render_kw={'placeholder': 'Title of the thing being reviewed'},
  )
  review_subject_creator = StringField(
    'Author / Director / Artist',
    validators=[Optional(), Length(max=200)],
    render_kw={'placeholder': 'Creator (optional)'},
  )
  review_subject_year = IntegerField(
    'Year',
    validators=[Optional(), NumberRange(min=1, max=9999)],
    render_kw={'placeholder': 'Year (optional)'},
  )

  # Project-specific fields — only used when post_type == 'project'.
  project_status = SelectField(
    'Project Status',
    choices=[
      ('in_progress', 'In Progress'),
      ('completed', 'Completed'),
      ('abandoned', 'Abandoned'),
    ],
    default='in_progress',
  )
  project_github_url = StringField(
    'GitHub URL',
    validators=[Optional(), URL(), Length(max=500)],
    render_kw={'placeholder': 'https://github.com/…'},
  )

  # Accepts multiple files via the multiple HTML attribute.
  images = FileField(
    'Upload Images',
    validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Images only!')],
    render_kw={'multiple': True, 'accept': 'image/*'},
  )
  submit = SubmitField('Save Post')

  def __init__(self, *args, **kwargs):
    """Populate category choices from the database at form instantiation time."""
    super(PostForm, self).__init__(*args, **kwargs)
    self.categories.choices = [(c.category_id, c.name) for c in Category.query.all()]


class ImageForm(FlaskForm):
  """
  Standalone form for uploading a single image with accessibility metadata.

  alt_text is Optional so editors are not blocked from uploading, but it
  should always be filled in before a post is published.
  """
  image_file = FileField(
    'Image',
    validators=[
      FileRequired(),
      FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Images only!'),
    ],
  )
  alt_text = StringField(
    'Alt Text',
    validators=[Optional(), Length(max=300)],
    render_kw={'placeholder': 'Describe the image for accessibility'},
  )
  caption = TextAreaField(
    'Caption',
    validators=[Optional(), Length(max=500)],
    render_kw={'placeholder': 'Image caption (optional)'},
  )
  is_featured = BooleanField('Set as Featured Image')
  submit = SubmitField('Upload Image')


class ImageEditForm(FlaskForm):
  """
  Form for editing an existing image's metadata.

  CSRF is handled automatically via FlaskForm; no manual validate_csrf() call
  is needed in the route.  file_size validation is not needed here because no
  file is being uploaded.
  """
  alt_text = StringField(
    'Alt Text',
    validators=[Optional(), Length(max=300)],
    render_kw={'placeholder': 'Describe the image for accessibility'},
  )
  caption = TextAreaField(
    'Caption',
    validators=[Optional(), Length(max=500)],
    render_kw={'placeholder': 'Image caption (optional)'},
  )
  is_featured = BooleanField('Set as Featured Image')
  submit = SubmitField('Save Changes')


class CategoryForm(FlaskForm):
  """Form for creating and editing a category."""
  name = StringField('Name', validators=[DataRequired(), Length(min=1, max=100)])
  description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
  submit = SubmitField('Save Category')


class ChangePasswordForm(FlaskForm):
  """
  Form for the logged-in admin to change their own password.

  current_password is verified against the stored hash before the new
  password is accepted, so a stolen session alone is not enough to lock
  out the real owner.
  """
  current_password = PasswordField('Current Password', validators=[DataRequired()])
  new_password = PasswordField('New Password', validators=[
    DataRequired(),
    Length(min=8),
    Regexp(
      r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)',
      message='Password must contain at least one uppercase letter, one lowercase letter, and one digit.',
    ),
  ])
  confirm_password = PasswordField('Confirm New Password', validators=[DataRequired()])
  submit = SubmitField('Change Password')


class ImportForm(FlaskForm):
  """
  Form for uploading a posts_export.json file via the admin panel.

  Accepts only .json files.  The file is processed in-memory; nothing is
  written to disk on the server.
  """
  json_file = FileField(
    'Export JSON file',
    validators=[FileRequired(), FileAllowed(['json'], 'JSON files only.')],
  )
  submit = SubmitField('Import')


class TotpVerifyForm(FlaskForm):
  """
  Form for entering a 6-digit TOTP code during login or 2FA setup.

  The code field accepts digits only; the validator is intentionally loose
  so that leading zeros are not stripped before pyotp checks the value.
  """
  code = StringField(
    'Authenticator code',
    validators=[
      DataRequired(),
      Length(min=6, max=6),
      Regexp(r'^[0-9]{6}$', message='Code must be exactly 6 digits.'),
    ],
    render_kw={'placeholder': '000000', 'autocomplete': 'one-time-code',
               'inputmode': 'numeric', 'pattern': '[0-9]{6}'},
  )
  submit = SubmitField('Verify')


class FootnoteForm(FlaskForm):
  """
  Form for adding or editing a footnote attached to a post.

  source_id and ref_post_id are both optional; a footnote may cite an
  external source, reference another post on the blog, or stand alone as
  a pure annotation.  Choices for both selects are populated dynamically
  in __init__ based on the current post's sources and all published posts.
  """
  content = TextAreaField(
    'Note',
    validators=[DataRequired()],
    render_kw={'rows': 3, 'placeholder': 'Footnote text…'},
  )
  source_id = SelectField(
    'Link to Source (optional)',
    coerce=int,
    validators=[Optional()],
  )
  ref_post_id = SelectField(
    'Cross-reference Post (optional)',
    coerce=int,
    validators=[Optional()],
  )
  submit = SubmitField('Save Footnote')

  def __init__(self, post_sources=None, *args, **kwargs):
    """
    Populate source and post choices dynamically.

    post_sources should be the list of Source objects for the current post.
    All published posts are available as cross-reference targets.
    The sentinel value 0 means "no selection" for both selects.
    """
    super(FootnoteForm, self).__init__(*args, **kwargs)
    source_choices = [(0, '— none —')]
    if post_sources:
      source_choices += [(s.source_id, f'{s.author}: {s.title}') for s in post_sources]
    self.source_id.choices = source_choices

    post_choices = [(0, '— none —')]
    post_choices += [
      (p.id, p.title)
      for p in Post.query.filter(Post.status == 'published').order_by(Post.title).all()
    ]
    self.ref_post_id.choices = post_choices


class SourceForm(FlaskForm):
  """
  Form for adding a bibliographic source to a post.

  author and title are required.  All other fields are optional but
  should be filled in as completely as possible for accurate citations.
  """
  author = StringField('Author', validators=[DataRequired(), Length(max=200)])
  title = StringField('Title', validators=[DataRequired(), Length(max=300)])
  publisher = StringField('Publisher', validators=[Optional(), Length(max=200)])
  year = IntegerField(
    'Year',
    validators=[Optional(), NumberRange(min=1, max=9999)],
    render_kw={'placeholder': 'e.g. 2024'},
  )
  url = StringField(
    'URL',
    validators=[Optional(), URL(), Length(max=500)],
    render_kw={'placeholder': 'https://…'},
  )
  isbn = StringField('ISBN', validators=[Optional(), Length(max=50)])
  page_range = StringField(
    'Pages',
    validators=[Optional(), Length(max=20)],
    render_kw={'placeholder': 'e.g. 23 or 23-45'},
  )
  submit = SubmitField('Save Source')


class BlueskyPostForm(FlaskForm):
  """
  Confirmation form for cross-posting a blog post excerpt to Bluesky.

  custom_text is optional: when left blank the route uses the post's title
  and excerpt.  When filled in it replaces the auto-generated body entirely
  (still truncated server-side to fit Bluesky's 300-grapheme limit).
  CSRF is automatic via FlaskForm.
  """
  custom_text = TextAreaField(
    'Custom post text (optional)',
    validators=[Optional(), Length(max=260)],
    render_kw={
      'rows': 4,
      'placeholder': 'Leave blank to use the post title and excerpt automatically.',
    },
  )
  submit = SubmitField('Post to Bluesky')


class DeleteFootnoteForm(FlaskForm):
  """
  Minimal form used only for CSRF validation when deleting a footnote.

  No fields are needed — the footnote ID comes from the URL.  Inheriting
  from FlaskForm is what adds and validates the hidden CSRF token field.
  """
  submit = SubmitField('Delete')


class DeleteSourceForm(FlaskForm):
  """
  Minimal form used only for CSRF validation when deleting a source.

  No fields are needed — the source ID comes from the URL.  Inheriting
  from FlaskForm is what adds and validates the hidden CSRF token field.
  """
  submit = SubmitField('Delete')
