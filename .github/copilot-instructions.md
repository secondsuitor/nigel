# Copilot Instructions

> General base principles (code style, security checklist, dependency rules, testing basics) live in the user-level instructions file (`base-principles.instructions.md`) and apply automatically. This file contains only what is specific to this project.

## Project Overview
Personal blog website rebuilt from https://github.com/secondsuitor/nigel — a single-user blog for essays, data analysis, and living resume.

**Current Phase**: Rapid rebuild and WordPress import (preserve dates, single author)  
**Tech Stack**: Python Flask + PostgreSQL + minimal JS on Gandi.net hosting (Python 3.13, PostgreSQL 11)

## Architecture Principles

### Core Constraints
- **Hosting Environment**: Gandi.net Simple+ hosting (Python 3.13, PostgreSQL 11 only)
- **Deployment**: Git-based deployment via Gandi's Git integration
- **Dependencies**: Minimal external libraries — vet each for security/necessity
- **Privacy**: No external data processing, all user interaction stays local
- **Auditability**: Every line must be readable and documented

### Design Philosophy
- Minimalist design prioritising readability and security
- State-driven interactions based on user patterns
- Rapid feature iteration with robust data model
- Everything cross-referenced and traceable

## Development Workflow

### File Structure
```
/
├── app/
│   ├── __init__.py     # App factory (create_app), extension instances
│   ├── routes.py       # All Flask routes (single blueprint: main)
│   ├── models.py       # SQLAlchemy models
│   ├── forms.py        # WTForms form classes
│   ├── atproto_utils.py
│   └── image_utils.py
├── templates/          # Jinja2 templates (minimal JS)
├── static/             # CSS and minimal client assets
├── migrations/         # Flask-Migrate scripts
├── tests/
│   ├── conftest.py     # Shared fixtures (see Test Architecture below)
│   ├── test_auth.py
│   ├── test_posts.py
│   ├── test_security.py
│   ├── test_import_export.py
│   └── test_atproto.py
├── requirements.txt    # Minimal dependency list
└── pytest.ini          # testpaths = tests, --tb=short
```

### Database Patterns
- PostgreSQL; design for quick table additions
- Single author — all content attributed to the site owner
- Design for future features: temperature logging, citation system, writing analytics
- **Current Schema Issues**: See `schema-review.md` — missing timestamps, WordPress import fields, analytics tables
- **Key Requirements**: Preserve original WordPress publication dates, SEO-friendly URLs, citation system

### Deployment
```bash
git push gandi main
```

## Flask Development Patterns

- App factory pattern (`create_app()`) — no module-level app instance
- Minimal to no JavaScript — server-side rendering preferred
- Every admin route must use `@admin_required` (not just `@login_required`)
- Direct PostgreSQL queries over ORM when performance matters
- All dates must preserve original WordPress timestamps

### Future Feature Planning
When implementing new features, consider these planned additions:
- Data analysis pipelines (temperature vs writing frequency correlation)
- Citation/footnote system with cross-references
- AT Protocol integration for Bluesky cross-posting
- Static site generation layer
- Multi-voice writing system (contrarian AI responses)

## Testing

**Run after every change**: `.venv/bin/python3.13 -m pytest tests/ -v`

### When to update tests
- **New route**: add a test covering happy path, unauthenticated redirect, and error branches.
- **New form field**: update import/export tests if the field appears in the JSON schema; update form submission tests to include the new field in POST data.
- **New model column**: add the column to fixture data in `conftest.py` if it has `NOT NULL` or a validator.
- **New extension initialised in `create_app()`**: import it in `conftest.py` and disable it in the `app` fixture if it would interfere with tests (e.g. rate limiters, CSRF).
- **Changed flash message text**: update the `assert b'...' in response.data` assertion in the matching test.
- **Changed route URL**: update every `client.get/post(...)` call that references the old URL.

### Test Architecture (do not change these patterns)

The test suite uses **SQLite temp file** (not `:memory:`) because each DB connection to an in-memory SQLite database sees an empty schema — routes and fixtures would be on different connections.

```python
# conftest.py — module level, BEFORE any 'from app import ...'
_db_fd, _db_path = tempfile.mkstemp(suffix='.db')
os.close(_db_fd)
os.environ['DATABASE_URL'] = f'sqlite:///{_db_path}'
```

**Fixture rules**:
- `app` fixture is `scope='session'` — one app for the whole run.
- `db_session` fixture is `scope='function'` — calls `drop_all()/create_all()` per test for full isolation.
- All fixtures that create ORM objects **must return the integer primary key**, not the ORM instance. Returning an instance causes `DetachedInstanceError` when accessed outside the creating session context.
- Never wrap test-client calls in `with app.app_context()`. Flask 3.x manages context per request; nesting causes "Popped wrong app context".

**Disabling extensions for tests** (set in the session-scoped `app` fixture):
```python
test_app.config.update({
  'TESTING': True,
  'WTF_CSRF_ENABLED': False,   # re-enabled per-test in TestCsrf
  'SESSION_COOKIE_SECURE': False,
  'RATELIMIT_ENABLED': False,
})
limiter.enabled = False  # must set directly; init_app() already ran
```

**File uploads in tests** must use `io.BytesIO`, not raw `bytes`:
```python
# Correct
data={'json_file': (io.BytesIO(payload), 'export.json', 'application/json')}
# Wrong — FileRequired() validator will fail
data={'json_file': (payload, 'export.json', 'application/json')}
```

**CSRF tests**: temporarily set `app.config['WTF_CSRF_ENABLED'] = True` and restore in a `finally` block. `CSRFProtect` reads config per-request via `before_request`, so this works reliably.

## Security — Flask-Specific Rules

These extend the base security principles with Flask/WTForms requirements.

- **CSRF**: `CSRFProtect` is initialised in `create_app()` and active on all state-changing routes. Do not exempt routes from CSRF without a documented reason. All POST forms must include `{{ csrf_token() }}`.
- **Authentication**: All admin routes use the `@admin_required` decorator. Do not use `@login_required` alone — it does not check the admin flag.
- **Session hardening**: `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, and `SESSION_COOKIE_SAMESITE = 'Lax'` are set in `create_app()`. Do not remove or weaken these.
- **Password hashing**: Always use `user.set_password()` / `user.check_password()` — never store or compare plaintext passwords.
- **TOTP 2FA**: The login flow requires a second factor when `totp_secret` is set. Do not add shortcuts that bypass `login/verify`.
- **HTML sanitisation**: All user-supplied HTML is sanitised with `bleach` before being stored. Do not render unsanitised input with `| safe`.
- **Secret key**: `SECRET_KEY` must come from the environment variable. The app raises `RuntimeError` if it is missing. Do not add a hardcoded fallback.
- **Credentials**: `BSKY_HANDLE` and `BSKY_APP_PASSWORD` come from environment variables. Never hardcode credentials or log them.
- Any new form must use `FlaskForm` (inherits CSRF field automatically).
- Any new file upload must use `FileAllowed` to validate the extension.
- `test_security.py` must still pass after every change — the CSRF and auth tests cover the core controls.

### What the test suite covers
- `test_auth.py` — login, logout, TOTP 2FA, safe `next=` redirect
- `test_security.py` — unauthenticated redirect for all admin routes, CSRF rejection on login and delete
- `test_posts.py` — admin-only access to create/edit/delete
- `test_import_export.py` — import authentication, file validation

## Import/Migration Notes
- WordPress backup import must preserve original publication dates
- Single author assumption (all content attributed to site owner)
- Content format conversion from WordPress to Flask template system