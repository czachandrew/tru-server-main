# E-commerce Alternative Product Platform

A platform for showing alternative product options and managing inventory from multiple vendors.

## Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment
4. Install dependencies: `pip install -r requirements.txt`
5. Configure your `.env` file with database and other settings
6. Run migrations: `python manage.py migrate`
7. Create a superuser: `python manage.py createsuperuser`
8. Start the Django server: `python manage.py runserver`
9. Start the Django-Q cluster: `python manage.py qcluster`

## Key Features

- Product management with multi-vendor support
- Price comparison from different vendors
- Affiliate link tracking
- GraphQL API for flexible data access
- Asynchronous data processing with Django-Q

## Architecture

This project uses:
- Django for the backend framework
- PostgreSQL for the database
- GraphQL for the API layer
- Django-Q for asynchronous task processing