# Database Schema Review and Recommendations

## Current Schema Issues

### 1. **Missing Critical Timestamps**
- No `created_at`, `updated_at`, `published_at` fields
- Need to preserve original WordPress dates during import (backdateable posts, one time import)

### 2. **WordPress Import Limitations** 
- Importing (one-time) from from_secondsuitor_dot_com/backup-secondsuitor-20250608-114356-GARA1jQIh4oNUBdFUR8RWXjjzLh3Ma.sql

### 3. **Single-User Optimization Needed**
- Make single-user
- Reduce user authentication complexity
- Add authenticator

### 4. **Missing Content Management Fields**
- Add `status` field (draft, published, archived)
- Add `slug` field for SEO-friendly URLs  
- Add `excerpt` or `meta_description` for SEO and AT cross-posting
- Add Add `categories` system

### 5. **Future Analytics Tables Missing**
- Add framework for future table additions

## Recommended New Schema

```python
from datetime import datetime
from app import db

class Post(db.Model):
    # Primary fields
    post_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.Text, nullable=True)
    
    # Status and metadata
    status = db.Column(db.String(20), default='draft')  # draft, published, archived
    post_type = db.Column(db.String(50), default='post')  # post, essay, analysis, resume
    
    # Timestamps (preserve WordPress dates)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime, nullable=True)
    wordpress_date = db.Column(db.DateTime, nullable=True)  # Original WP publication date
    
    # WordPress import tracking
    wordpress_id = db.Column(db.Integer, nullable=True)
    wordpress_url = db.Column(db.String(500), nullable=True)
    
    # SEO and social
    meta_description = db.Column(db.String(300), nullable=True)
    featured_image = db.Column(db.String(500), nullable=True)
    
    # Relationships
    tags = db.relationship('Tag', secondary='post_tags', backref='posts')
    sources = db.relationship('Source', backref='post', cascade='all, delete-orphan')
    footnotes = db.relationship('Footnote', backref='post', cascade='all, delete-orphan')

class Tag(db.Model):
    tag_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)

# Association table for many-to-many relationship
post_tags = db.Table('post_tags',
    db.Column('post_id', db.Integer, db.ForeignKey('post.post_id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.tag_id'), primary_key=True)
)

class Source(db.Model):
    source_id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    publisher = db.Column(db.String(200), nullable=True)
    year = db.Column(db.Integer, nullable=True)
    url = db.Column(db.String(500), nullable=True)
    isbn = db.Column(db.String(50), nullable=True)
    page_range = db.Column(db.String(20), nullable=True)  # "23-45" or "23"

class Footnote(db.Model):
    footnote_id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey('source.source_id'), nullable=True)
    anchor_text = db.Column(db.String(100), nullable=True)  # Text that triggers footnote

# Analytics tables for future features
class WritingSession(db.Model):
    session_id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    word_count = db.Column(db.Integer, default=0)
    temperature_celsius = db.Column(db.Float, nullable=True)
    mood_rating = db.Column(db.Integer, nullable=True)  # 1-10 scale
    post_id = db.Column(db.Integer, db.ForeignKey('post.post_id'), nullable=True)

class DailyMetrics(db.Model):
    date = db.Column(db.Date, primary_key=True)
    words_written = db.Column(db.Integer, default=0)
    avg_temperature = db.Column(db.Float, nullable=True)
    sessions_count = db.Column(db.Integer, default=0)
    mood_avg = db.Column(db.Float, nullable=True)

# Remove User model entirely - single author blog
```

## Migration Strategy

1. **Preserve Current Data**: Export existing posts before schema change
2. **WordPress Import**: Create import script using `wordpress_date` field
3. **URL Compatibility**: Generate slugs that match current URL structure
4. **Analytics Setup**: Start logging temperature/writing data immediately

## Implementation Status

**COMPLETED**: Updated `models.py` with new schema (see `migration-notes.md`)

## Next Steps

1. **Create database migration script** for existing data preservation
2. **Build WordPress import functionality** for `backup-secondsuitor-20250608-114356-GARA1jQIh4oNUBdFUR8RWXjjzLh3Ma.sql`
3. **Update Flask routes and templates** for new model structure
4. **Set up analytics data collection** framework