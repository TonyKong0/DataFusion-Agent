"""Single source of truth for the application version.

The backend reports this value through /api/health; the frontend renders it from
that response, and release documents point at the same number. Update it here and
in package.json together (a regression test enforces the pair stays aligned).
"""

APP_VERSION = '1.8.0'
