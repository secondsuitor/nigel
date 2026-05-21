import os
import re
from datetime import timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

# Extensions are initialised here and bound to the app inside create_app(),
# so they can be imported by models and routes without circular dependencies.
db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
  key_func=get_remote_address,
  # In-memory storage is fine for a single-process Gandi.net deployment.
  # If the process restarts, counters reset — acceptable for a personal blog.
  # Switch to storage_uri="redis://..." if a Redis instance becomes available.
  storage_uri='memory://',
  # Default limit applied to every route unless overridden with @limiter.limit().
  # Most public routes are read-only so this is intentionally generous.
  default_limits=['200 per day', '60 per hour'],
)


def create_app():
  """
  Application factory.

  Returns a configured Flask app instance.  Using a factory lets tests and
  the Gandi WSGI harness each create their own app without shared state.
  """
  app = Flask(__name__)

  # Secret key is required for CSRF and session signing.
  # Must be set via the SECRET_KEY environment variable in every environment.
  # The app refuses to start without it so a weak fallback can never slip
  # into production unnoticed.
  secret_key = os.environ.get('SECRET_KEY')
  if not secret_key:
    raise RuntimeError(
      'SECRET_KEY environment variable is not set. '
      'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
    )
  app.config['SECRET_KEY'] = secret_key

  # Gandi.net provides DATABASE_URL for PostgreSQL.
  # Fall back to a local SQLite file for development.
  database_url = os.environ.get('DATABASE_URL')
  if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
  else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "blog.db")}'

  # Disable modification tracking - we don't use it and it adds overhead.
  app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

  # Session cookie hardening.
  # Secure: only send over HTTPS (Gandi.net terminates TLS).
  # HttpOnly: JavaScript cannot read the cookie (reduces XSS impact).
  # SameSite Lax: blocks cross-site POST CSRF while allowing normal navigation.
  # Lifetime: sessions expire after 1 hour of inactivity.
  app.config['SESSION_COOKIE_SECURE'] = True
  app.config['SESSION_COOKIE_HTTPONLY'] = True
  app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
  app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

  # Bind extensions to this app instance.
  db.init_app(app)
  migrate.init_app(app, db)
  login.init_app(app)
  csrf.init_app(app)
  limiter.init_app(app)

  # Flask-Login configuration.
  login.login_view = 'main.login'
  login.login_message = 'Please log in to access admin features.'
  login.login_message_category = 'info'

  @login.user_loader
  def load_user(user_id):
    """Load user by primary key for Flask-Login session management."""
    from app.models import User
    return db.session.get(User, int(user_id))

  # Models must be imported before create_all() so SQLAlchemy knows the schema.
  from app import models  # noqa: F401

  # Register the main blueprint which contains all routes.
  from app.routes import main as main_blueprint
  app.register_blueprint(main_blueprint)

  # Jinja2 filter: converts [^N] markers in post content to superscript links.
  # Applied in templates via {{ post.content | render_footnote_markers | safe }}.
  def render_footnote_markers(content):
    """Replace [^N] with <sup><a href="#fn-N">[N]</a></sup> for in-content markers."""
    return re.sub(
      r'\[\^(\d+)\]',
      r'<sup><a href="#fn-\1" id="fnref-\1">[\1]</a></sup>',
      content,
    )
  app.jinja_env.filters['render_footnote_markers'] = render_footnote_markers


  return app
