# Project Status

_Last updated: May 18, 2026_

---

## What this codebase is

Personal blog rebuilt from scratch (migrated from secondsuitor.com WordPress instance). Single-user Flask app hosted on Gandi.net Simple+ (Python 3.13, PostgreSQL 11). The rebuild goals were: preserve original WordPress publication dates, add a citation/footnote system, integrate AT Protocol cross-posting to Bluesky, and keep the codebase small enough to be fully auditable.

---

## Session: May 18, 2026 — Security hardening and model refactor

### Rationale

A full refactor analysis flagged several issues worth fixing before the first production deploy:

1. **is_active not enforced** — `admin_required` checked `is_authenticated` but not `is_active`, meaning a deactivated account could still reach every admin route.
2. **edit_image used manual `validate_csrf()`** — one route used the low-level import rather than `FlaskForm.validate_on_submit()`. This was inconsistent and had no corresponding test.
3. **`| safe` usages undocumented** — three templates rendered stored HTML via `| safe` with no indication that the content had been sanitised by `bleach` before storage.
4. **Post/User PKs named `post_id`/`user_id`** — Python convention for primary keys is `.id`. The old names created confusion between the Post PK (`.post_id`) and FK columns on related models that are also legitimately named `post_id`. Renaming to `.id` makes the distinction clear without any schema migration.
5. **`WritingSession` and `DailyMetrics` were dead code** — never written to, never queried, creating misleading schema noise. The planned analytics feature will be designed properly when the time comes.

### What was done

#### Phase 1 — Auth hardening

- **`admin_required` decorator** (`app/routes.py`): added `is_active` check. Inactive users are now logged out and redirected to the login page rather than silently passing through.
- **`TestInactiveUser`** (`tests/test_security.py`): new test class covering the inactive-user redirect.

#### Phase 2 — CSRF pattern consistency and `| safe` documentation

- **`ImageEditForm`** (`app/forms.py`): new `FlaskForm` subclass with `alt_text`, `caption`, and `is_featured` fields.
- **`edit_image` route** (`app/routes.py`): rewrote from manual `validate_csrf()` + raw `request.form` access to `ImageEditForm.validate_on_submit()`. Removed the bare `validate_csrf` import from this code path.
- **`edit_image.html`** (`app/templates/edit_image.html`): created — this template was missing entirely; the route was rendering a non-existent file.
- **`| safe` comments** (`home.html`, `category.html`, `post.html`): added Jinja2 comments above every `| safe` usage confirming the content was sanitised by `bleach.clean()` before storage.

#### Phase 3 — Model rename and dead code removal

Strategy: SQLAlchemy column aliases (`id = db.Column('post_id', db.Integer, primary_key=True)`) — the DB column name stays unchanged so no Alembic migration is needed. Only the Python attribute name changes.

**`app/models.py`**
- `Post.post_id` → `Post.id` (alias to DB column `post_id`)
- `User.user_id` → `User.id` (alias to DB column `user_id`)
- `User.get_id()` and both `__repr__` methods updated accordingly
- `WritingSession` class removed
- `DailyMetrics` class removed

**`app/routes.py`** — 7 call sites updated (`generate_slug`, `api_posts`, `login`, `new_post` ×2, `edit_post`, `upload_image`)

**`app/forms.py`** — 1 call site updated (footnote cross-reference choices)

**Templates** — 12 occurrences of `post.post_id` updated across `admin_posts.html`, `edit_post.html`, `post.html`, `bluesky_post.html`, `upload_image.html`

**`tests/conftest.py`** — fixture return values updated (`user.id`, `post.id`)

**`tests/test_security.py`** — `TestInactiveUser` updated

### Result

70/70 tests passing. Clean working tree. Initial commit made (`de5f873`).

---

## Current architecture

```
app/
  __init__.py          # create_app() factory; CSRFProtect, LoginManager, Limiter, Migrate
  models.py            # Post, User, Category, Image, Footnote, Source, ReviewMeta, ProjectMeta
  routes.py            # All views under the 'main' blueprint
  forms.py             # WTForms classes; every state-changing route uses FlaskForm
  atproto_utils.py     # Bluesky cross-posting via AT Protocol
  image_utils.py       # PIL-based resize/thumbnail on upload
  utility.py           # sanitise_html(), safe_next_url(), generate_slug()
templates/             # Jinja2; minimal JS; no frameworks
static/                # Bulma CSS + custom.css
migrations/            # Manual SQL scripts (no Alembic env.py)
tests/                 # pytest; SQLite temp-file DB; 70 tests
```

### Key design decisions

- **Single blueprint** (`main`) — all routes in one file. Split if the file grows beyond ~1 200 lines.
- **Column alias strategy** — `db.Column('post_id', ...)` lets Python use `.id` while keeping the DB column name stable. FK declarations reference the DB name (`'post.post_id'`) and remain valid.
- **No Alembic env.py** — migrations are plain Python scripts in `migrations/`. This was intentional during rapid schema iteration. Alembic can be added when the schema stabilises.
- **SQLite in dev/test, PostgreSQL in prod** — `DATABASE_URL` env var selects the engine. Tests use a SQLite temp file (not `:memory:`) to avoid multi-connection schema issues.
- **CSRF** — `CSRFProtect` globally active; disabled in test config via `WTF_CSRF_ENABLED = False`; re-enabled per-test in `TestCsrf`.
- **Rate limiting** — Flask-Limiter on login route; disabled in test config via `RATELIMIT_ENABLED = False` and `limiter.enabled = False`.

---

## Schema (models.py)

| Model | PK | Notes |
|---|---|---|
| `Post` | `id` (DB: `post_id`) | Slug-based URLs; supports `essay`, `review`, `project` types; `published_at` preserves WordPress dates |
| `User` | `id` (DB: `user_id`) | Single user; TOTP secret optional; `is_active` enforced by `admin_required` |
| `Category` | `category_id` | Many-to-many with Post via `post_categories` join table |
| `Image` | `image_id` | Belongs to Post via `post_id` FK; stores dimensions, file size, CDN URL |
| `Footnote` | `footnote_id` | Belongs to Post; optional `ref_post_id` cross-reference and `source_id` link |
| `Source` | `source_id` | Bibliographic record; belongs to Post |
| `ReviewMeta` | tied to `post_id` | One-to-one with Post for review-type posts |
| `ProjectMeta` | tied to `post_id` | One-to-one with Post for project-type posts |

---

## Deployment

**Host**: Gandi.net Simple+ — Python 3.13, PostgreSQL 11  
**Deploy command**: `git push gandi main`  
**Entry point**: `wsgi.py` → `create_app()`  
**Required env vars**: `SECRET_KEY`, `DATABASE_URL`, `BSKY_HANDLE`, `BSKY_APP_PASSWORD`

**Pre-deploy checklist**: run `check.sh` (or manually: tests green, no DEBUG=True, no hardcoded secrets, requirements pinned, clean working tree, .env not committed).

**Migration notes**: The `migrations/` scripts (`add_bluesky_uri.py`, `add_content_types.py`, `add_totp_secret.py`, `migrate_schema.py`) are manual. After each deploy, verify which scripts have been applied to the production DB and run outstanding ones via `flask shell` or `psql`.

---

## Future work

### Near-term (before content publishing)

- **WordPress import**: `import_wordpress.py` parses the SQL dump in `from_secondsuitor_dot_com/`. Needs a test run against the backup file and verification that `published_at` dates are preserved correctly.
- **Gandi remote**: `git remote add gandi git+ssh://...@git.sd5.gpaas.net/default.git` — not yet configured.
- **Production DB migrations**: run the outstanding `migrations/` scripts against the Gandi PostgreSQL instance after first deploy.

### Medium-term

- **Alembic integration**: add `migrations/env.py` so `flask db current` / `flask db upgrade` work. The column alias strategy means existing data survives the switch with no changes.
- **Test coverage gaps**: `edit_image` route has no test (happy path, auth, CSRF). `api_posts` JSON response is untested. `bluesky_post` route is untested beyond auth.
- **`delete_footnote` and `delete_source`**: still use manual `validate_csrf()` rather than a `FlaskForm`. Candidates for the next CSRF-pattern pass.
- **Image upload tests**: `test_import_export.py` covers JSON import; image upload has no test for the `FileAllowed` validator.

### Long-term / planned features

- **Data analysis pipeline**: temperature vs writing frequency correlation — the `WritingSession`/`DailyMetrics` tables were dropped as dead code. When this feature is built, design the schema intentionally with proper Alembic migrations.
- **Citation cross-references**: `Footnote.ref_post_id` exists; UI for navigating cross-referenced posts is not implemented.
- **Static site generation layer**: pre-render published posts to static HTML for faster cold-start response on Gandi.
- **AT Protocol / Bluesky**: `atproto_utils.py` and the `bluesky_post` route exist; end-to-end test against the live Bluesky API is not yet done.
- **Multi-voice writing system**: contrarian AI responses to essays — not started.


## Changes Summary

### Database Schema Modernization
- **File**: `app/models.py` - Completely updated
- **Backup**: `app/models_backup.py` (original preserved)
- **Changes**:
  - Added timestamps (`created_at`, `updated_at`, `published_at`)
  - WordPress import fields (`wordpress_id`, `wordpress_url`, `wordpress_date`)
  - SEO fields (`slug`, `meta_description`, `excerpt`)
  - Categories system (many-to-many relationship)
  - Enhanced citation system with flexible Source model
  - Analytics tables (`WritingSession`, `DailyMetrics`)
  - Simplified User model for single-user blog

### Flask Routes Modernization
- **File**: `app/routes.py` - Completely rewritten
- **Backup**: `app/routes_backup.py` (original preserved)
- **New Features**:
  - Slug-based URLs (`/post/my-post-title` instead of `/post/123`)
  - Category pages (`/category/blog`)
  - Admin dashboard (`/admin`, `/admin/posts`, `/admin/categories`)
  - Content management (publish/unpublish, delete)
  - RSS feed (`/feed.xml`) and JSON API (`/api/posts`)
  - Backward compatibility for old post URLs

### Database Migration Tools
- **File**: `migrations/migrate_schema.py`
- **Purpose**: Preserves existing data while upgrading schema
- **Features**:
  - Automatic backup of existing data to JSON
  - Safe schema recreation
  - Data migration with slug generation
  - Error handling and rollback capability

### WordPress Import System
- **File**: `import_wordpress.py`
- **Target**: `backup-secondsuitor-20250608-114356-GARA1jQIh4oNUBdFUR8RWXjjzLh3Ma.sql`
- **Features**:
  - Parses WordPress SQL dumps
  - Preserves original publication dates
  - Content cleaning and sanitization
  - Category import
  - Duplicate detection and slug handling

### Template Updates
- **Updated Files**:
  - `app/templates/home.html` - Modern post listing with excerpts, categories
  - `app/templates/post.html` - Enhanced with footnotes, sources, metadata
  - `app/templates/category.html` - New category page
  - `app/templates/admin.html` - Admin dashboard
  - `app/templates/admin_posts.html` - Post management interface

### Form Enhancements
- **File**: `app/forms.py` - Enhanced with new fields
- **New Fields**: excerpt, meta_description, status, categories
- **Dynamic**: Category choices populated from database

### New Project Structure
```
/
├── app/
│   ├── models.py              # Updated schema
│   ├── routes.py              # Modernized routes  
│   ├── forms.py               # Enhanced forms
│   ├── routes_backup.py       # Original backup
│   └── templates/
│       ├── home.html          # Modern layout
│       ├── post.html          # Enhanced features
│       ├── category.html      # Category pages
│       ├── admin.html         # Admin dashboard
│       └── admin_posts.html   # Post management
├── migrations/
│   └── migrate_schema.py      # Migration script
├── import_wordpress.py        # WordPress import
├── schema-review.md           # Analysis & recommendations
├── migration-notes.md         # Implementation notes
└── .github/
    └── copilot-instructions.md # Updated AI instructions
```

## Key Architectural Changes

### Single-User Optimization
- Removed Flask-Login complexity
- Simplified authentication approach
- All posts belong to single author

### SEO & Content Management
- Slug-based URLs for better SEO
- Meta descriptions for social sharing
- Category organization system
- Draft/published status workflow

### WordPress Migration Ready
- Preserves original publication dates in `wordpress_date` field
- Handles content cleaning and conversion
- Category mapping and import
- Duplicate detection by WordPress ID

### Future-Proofed Analytics
- `WritingSession` table for temperature correlation
- `DailyMetrics` for productivity analysis  
- Extensible schema for new data types

## Ready for Testing

The application is now ready for testing with:
1. **Run migration**: `python migrations/migrate_schema.py`
2. **Import WordPress**: `python import_wordpress.py`
3. **Start Flask app**: Check `app/__init__.py` and `wsgi.py`

## Dependencies to Check
- `requirements.txt` may need updates for new packages
- `bleach` for content sanitization
- Form libraries (`flask-wtf`, `wtforms`)
- Database setup (PostgreSQL vs SQLite for development)

## Next Steps When Ready
1. Test database migration with existing data
2. Verify WordPress import functionality  
3. Test new admin interface
4. Check all URL routes work correctly
5. Validate content rendering and SEO features