web: gunicorn ecommerce_platform.wsgi:application --bind 0.0.0.0:$PORT
worker: python manage.py qcluster