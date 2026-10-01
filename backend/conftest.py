"""Pytest configuration for the backend test suite.

Tests run with fake Supabase/Gemini/Drive/Forms clients and must not require
real credentials. Provide safe defaults for settings that the app reads at
import time.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
