from django.core.management.base import BaseCommand
from ecommerce_platform.utils import clear_redis_tasks

class Command(BaseCommand):
    help = 'Clear all affiliate link tasks from Redis'

    def handle(self, *args, **options):
        count = clear_redis_tasks()
        self.stdout.write(self.style.SUCCESS(f'Successfully cleared {count} Redis keys'))