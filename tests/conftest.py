"""Isolate test signing keys from developer credentials; never persist them."""

import os
import secrets

# Set before test-module imports construct the application. Production-mode tests
# explicitly replace these settings and exercise startup rejection.
os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
os.environ["APP_ENV"] = "development"
