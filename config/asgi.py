"""
ASGI config for Suchar Overflow project.

This module contains the ASGI application used by uvicorn and any production
ASGI deployments. It should expose a module-level variable named ``application``.

"""

import os
import sys
from pathlib import Path

from django.core.asgi import get_asgi_application

# This allows easy placement of apps within the interior
# suchar_overflow directory.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "suchar_overflow"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
