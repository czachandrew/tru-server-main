from django.core.management.base import BaseCommand
from affiliates.tasks import requeue_pending_affiliate_links
from django.db import models
from affiliates.models import AffiliateLink

class Command(BaseCommand):
    help = 'Requeue affiliate links that are missing their affiliate URLs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--platform',
            type=str,
            help='Filter by platform (e.g., amazon)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of links to process',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only count links, do not requeue',
        )

    def handle(self, *args, **options):
        platform = options.get('platform')
        limit = options.get('limit')
        dry_run = options.get('dry_run')
        
        if dry_run:
            # Just count and report
            queryset = AffiliateLink.objects.filter(
                models.Q(affiliate_url='') | 
                models.Q(affiliate_url__startswith='ERROR:')
            )
            
            if platform:
                queryset = queryset.filter(platform=platform)
                
            count = queryset.count()
            self.stdout.write(f"Found {count} affiliate links to requeue")
            
            if platform:
                self.stdout.write(f"Platform filter: {platform}")
            
            if limit:
                self.stdout.write(f"Would process only {min(limit, count)} links due to limit={limit}")
        else:
            # Actually requeue
            results = requeue_pending_affiliate_links(platform, limit)
            
            self.stdout.write(self.style.SUCCESS(
                f"Requeued {results['success']} affiliate links, with {results['errors']} errors"
            ))
            
            if results['total_found'] > results['processed']:
                self.stdout.write(
                    f"Note: Only processed {results['processed']} out of {results['total_found']} found links"
                ) 