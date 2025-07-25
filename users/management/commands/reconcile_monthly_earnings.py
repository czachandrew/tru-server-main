"""
Management command for monthly reconciliation of affiliate earnings
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import calendar
import json
import logging

from users.services import ReconciliationService
from users.models import WalletTransaction, UserProfile
from affiliates.models import AffiliateLink


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run monthly reconciliation of projected vs actual affiliate earnings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=timezone.now().year,
            help='Year to reconcile (default: current year)'
        )
        parser.add_argument(
            '--month',
            type=int,
            default=timezone.now().month - 1 if timezone.now().month > 1 else 12,
            help='Month to reconcile (default: previous month)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be reconciled without making changes'
        )
        parser.add_argument(
            '--affiliate-platform',
            type=str,
            choices=['amazon', 'ebay', 'walmart', 'all'],
            default='all',
            help='Specific affiliate platform to reconcile'
        )
        parser.add_argument(
            '--min-revenue',
            type=float,
            default=0.01,
            help='Minimum revenue threshold for reconciliation'
        )

    def handle(self, *args, **options):
        year = options['year']
        month = options['month']
        dry_run = options['dry_run']
        platform = options['affiliate_platform']
        min_revenue = Decimal(str(options['min_revenue']))

        # Adjust year if month is 12 and we're in January
        if month == 12 and timezone.now().month == 1:
            year -= 1

        self.stdout.write(
            self.style.SUCCESS(f'Starting monthly reconciliation for {year}-{month:02d}')
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )

        try:
            # Run reconciliation
            results = self.run_reconciliation(year, month, platform, min_revenue, dry_run)
            
            # Display results
            self.display_results(results)
            
            # Create summary report
            if not dry_run:
                self.create_summary_report(results)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Reconciliation failed: {str(e)}')
            )
            logger.error(f'Monthly reconciliation failed: {str(e)}', exc_info=True)

    def run_reconciliation(self, year, month, platform, min_revenue, dry_run):
        """Run the actual reconciliation process"""
        
        # Define period
        period_start = datetime(year, month, 1)
        period_end = datetime(year, month, calendar.monthrange(year, month)[1])
        
        self.stdout.write(f'Reconciling period: {period_start.date()} to {period_end.date()}')
        
        # Get pending projected earnings in the period
        pending_query = WalletTransaction.objects.filter(
            transaction_type='EARNING_PROJECTED',
            status='PENDING',
            created_at__gte=period_start,
            created_at__lte=period_end
        )
        
        if platform != 'all':
            pending_query = pending_query.filter(
                affiliate_link__platform=platform
            )
        
        pending_transactions = pending_query.select_related(
            'user', 'affiliate_link'
        ).order_by('affiliate_link', 'user')
        
        self.stdout.write(f'Found {pending_transactions.count()} pending transactions')
        
        # Group by affiliate link
        affiliate_groups = {}
        for transaction in pending_transactions:
            affiliate_link = transaction.affiliate_link
            if affiliate_link not in affiliate_groups:
                affiliate_groups[affiliate_link] = []
            affiliate_groups[affiliate_link].append(transaction)
        
        # Process each affiliate link
        reconciliation_results = {
            'period': f'{year}-{month:02d}',
            'platform': platform,
            'processed_links': 0,
            'total_users_affected': 0,
            'total_projected': Decimal('0.00'),
            'total_actual': Decimal('0.00'),
            'total_adjustment': Decimal('0.00'),
            'link_results': []
        }
        
        for affiliate_link, transactions in affiliate_groups.items():
            # Get actual revenue for this affiliate link
            actual_revenue = self.get_actual_revenue(affiliate_link, period_start, period_end)
            
            if actual_revenue < min_revenue:
                self.stdout.write(
                    f'Skipping {affiliate_link} - revenue ${actual_revenue} below threshold'
                )
                continue
            
            # Calculate projections
            total_projected = sum(t.amount for t in transactions)
            users_affected = len(set(t.user for t in transactions))
            
            self.stdout.write(
                f'Processing {affiliate_link}: ${actual_revenue} actual vs ${total_projected} projected '
                f'({users_affected} users)'
            )
            
            if not dry_run:
                # Run actual reconciliation
                link_result = ReconciliationService.reconcile_affiliate_earnings(
                    affiliate_link, actual_revenue, period_start, period_end
                )
            else:
                # Simulate reconciliation
                link_result = {
                    'affiliate_link': affiliate_link,
                    'actual_revenue': actual_revenue,
                    'total_projected': total_projected,
                    'adjustment_amount': Decimal('0.00'),  # Would be calculated
                    'reconciled_users': []
                }
            
            reconciliation_results['link_results'].append(link_result)
            reconciliation_results['processed_links'] += 1
            reconciliation_results['total_users_affected'] += users_affected
            reconciliation_results['total_projected'] += total_projected
            reconciliation_results['total_actual'] += actual_revenue
            reconciliation_results['total_adjustment'] += link_result['adjustment_amount']
        
        return reconciliation_results

    def get_actual_revenue(self, affiliate_link, period_start, period_end):
        """
        Get actual revenue for an affiliate link during the period
        In a real implementation, this would query affiliate program APIs
        """
        # For now, use the revenue field from the affiliate link
        # In production, you'd integrate with affiliate program APIs
        
        # Check if we have confirmed transactions for this period
        confirmed_revenue = WalletTransaction.objects.filter(
            affiliate_link=affiliate_link,
            transaction_type='EARNING_CONFIRMED',
            created_at__gte=period_start,
            created_at__lte=period_end
        ).aggregate(
            total=sum('amount')
        )['total'] or Decimal('0.00')
        
        if confirmed_revenue > 0:
            # If we have confirmed transactions, use those
            return confirmed_revenue
        
        # Otherwise, use the affiliate link's revenue field
        # This would be updated by API integrations
        return affiliate_link.revenue or Decimal('0.00')

    def display_results(self, results):
        """Display reconciliation results"""
        self.stdout.write(
            self.style.SUCCESS(f"\n=== Reconciliation Results for {results['period']} ===")
        )
        
        self.stdout.write(f"Platform: {results['platform']}")
        self.stdout.write(f"Processed Links: {results['processed_links']}")
        self.stdout.write(f"Users Affected: {results['total_users_affected']}")
        self.stdout.write(f"Total Projected: ${results['total_projected']}")
        self.stdout.write(f"Total Actual: ${results['total_actual']}")
        self.stdout.write(f"Total Adjustment: ${results['total_adjustment']}")
        
        if results['total_projected'] > 0:
            accuracy = (results['total_actual'] / results['total_projected']) * 100
            self.stdout.write(f"Projection Accuracy: {accuracy:.1f}%")
        
        # Show individual link results
        if results['link_results']:
            self.stdout.write("\n=== Individual Link Results ===")
            for link_result in results['link_results']:
                affiliate_link = link_result['affiliate_link']
                self.stdout.write(
                    f"\n{affiliate_link.platform} - {affiliate_link.platform_id}:"
                )
                self.stdout.write(f"  Actual Revenue: ${link_result['actual_revenue']}")
                self.stdout.write(f"  Projected Total: ${link_result['total_projected']}")
                self.stdout.write(f"  Adjustment: ${link_result['adjustment_amount']}")
                
                if link_result.get('reconciled_users'):
                    self.stdout.write(f"  Users Reconciled: {len(link_result['reconciled_users'])}")

    def create_summary_report(self, results):
        """Create a summary report of reconciliation"""
        try:
            # Create a reconciliation transaction for record keeping
            summary_transaction = WalletTransaction.objects.create(
                user=None,  # System transaction
                transaction_type='RECONCILIATION',
                amount=results['total_adjustment'],
                balance_before=Decimal('0.00'),
                balance_after=Decimal('0.00'),
                description=f"Monthly reconciliation for {results['period']}",
                status='CONFIRMED',
                processed_at=timezone.now(),
                metadata={
                    'period': results['period'],
                    'platform': results['platform'],
                    'processed_links': results['processed_links'],
                    'users_affected': results['total_users_affected'],
                    'total_projected': str(results['total_projected']),
                    'total_actual': str(results['total_actual']),
                    'total_adjustment': str(results['total_adjustment']),
                    'link_count': len(results['link_results'])
                }
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"Created summary report: Transaction ID {summary_transaction.id}")
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to create summary report: {str(e)}")
            )

    def send_reconciliation_notifications(self, results):
        """Send notifications about reconciliation results"""
        # This would send notifications to admins about reconciliation results
        # Implementation depends on your notification system
        pass


class AffiliateRevenueUpdater:
    """Helper class to update affiliate revenue from external APIs"""
    
    @staticmethod
    def update_amazon_revenue(affiliate_link, start_date, end_date):
        """Update Amazon affiliate revenue for a specific period"""
        # This would integrate with Amazon Associates API
        # For now, return placeholder data
        return {
            'revenue': Decimal('10.50'),
            'clicks': 25,
            'conversions': 2,
            'updated_at': timezone.now()
        }
    
    @staticmethod
    def update_ebay_revenue(affiliate_link, start_date, end_date):
        """Update eBay affiliate revenue for a specific period"""
        # This would integrate with eBay Partner Network API
        return {
            'revenue': Decimal('8.75'),
            'clicks': 15,
            'conversions': 1,
            'updated_at': timezone.now()
        }
    
    @staticmethod
    def update_all_affiliate_revenue(start_date, end_date):
        """Update revenue for all affiliate links in a period"""
        updated_count = 0
        
        affiliate_links = AffiliateLink.objects.filter(
            is_active=True,
            wallet_transactions__created_at__gte=start_date,
            wallet_transactions__created_at__lte=end_date
        ).distinct()
        
        for link in affiliate_links:
            try:
                if link.platform == 'amazon':
                    revenue_data = AffiliateRevenueUpdater.update_amazon_revenue(
                        link, start_date, end_date
                    )
                elif link.platform == 'ebay':
                    revenue_data = AffiliateRevenueUpdater.update_ebay_revenue(
                        link, start_date, end_date
                    )
                else:
                    continue
                
                # Update the affiliate link
                link.revenue = revenue_data['revenue']
                link.clicks = revenue_data['clicks']
                link.conversions = revenue_data['conversions']
                link.save()
                
                updated_count += 1
                
            except Exception as e:
                logger.error(f"Failed to update revenue for {link}: {e}")
        
        return updated_count 