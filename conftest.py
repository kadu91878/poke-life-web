from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / 'backend'
VENV_LIB_DIR = BACKEND_DIR / '.venv' / 'lib'
SITE_PACKAGES = next(VENV_LIB_DIR.glob('python*/site-packages'), None)

for candidate in (BACKEND_DIR, SITE_PACKAGES):
    if candidate and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()
