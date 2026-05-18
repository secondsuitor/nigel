#!/usr/bin/env python3
"""
WSGI entry point for the Flask blog application.

Gandi.net requires the callable to be named 'application'.
When run directly it starts the Flask development server, reading PORT and
FLASK_ENV from the environment so the same file works on both local and CI
environments without modification.
"""

import os

from app import create_app

# Gandi.net's WSGI runner imports this module and calls application().
application = create_app()

# SESSION_COOKIE_SECURE=True (set in __init__.py) requires HTTPS.
# Gandi.net terminates TLS so cookies arrive over HTTPS in production.
# In local development the dev server uses plain HTTP, which causes Flask
# to silently refuse to set the session cookie and break login entirely.
# Override the flag here when FLASK_ENV=development so the local server
# works without changing any production config.
if os.environ.get('FLASK_ENV') == 'development':
  application.config['SESSION_COOKIE_SECURE'] = False

if __name__ == '__main__':
  debug = os.environ.get('FLASK_ENV') == 'development'
  port = int(os.environ.get('PORT', 5000))
  application.run(host='0.0.0.0', port=port, debug=debug)
