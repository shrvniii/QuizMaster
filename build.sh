#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Compile static files (CSS, JS)
python manage.py collectstatic --no-input

# Run database migrations
python manage.py migrate

# Automatically create the superuser if it doesn't exist
python -c "import django; django.setup(); from django.contrib.auth.models import User; User.objects.create_superuser('admin', 'admin@example.com', 'admin123') if not User.objects.filter(username='admin').exists() else None"
