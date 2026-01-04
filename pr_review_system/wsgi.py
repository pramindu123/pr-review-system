"""
WSGI config for GitHub PR Review System.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pr_review_system.settings')

application = get_wsgi_application()
