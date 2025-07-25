from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal

from users.models import PayoutRequest
from users.mock_payout_service import PayoutProcessor
from users.tasks import PayoutTaskManager


class Command(BaseCommand):
    help = 'Process pending payout requests (for testing without Django Q worker)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--payout-id',
            type=int,
            help='Process a specific payout by ID',
        )
        parser.add_argument(
            '--status',
            type=str,
            default='approved',
            help='Process payouts with specific status (default: approved)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Maximum number of payouts to process (default: 10)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually processing',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Payout Processing Command Started')
        )

        if options['payout_id']:
            # Process specific payout
            try:
                payout = PayoutRequest.objects.get(id=options['payout_id'])
                self._process_single_payout(payout, options['dry_run'])
            except PayoutRequest.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"❌ Payout #{options['payout_id']} not found")
                )
                return

        else:
            # Process multiple payouts by status
            payouts = PayoutRequest.objects.filter(
                status=options['status']
            ).order_by('requested_at')[:options['limit']]

            if not payouts:
                self.stdout.write(
                    self.style.WARNING(f"📭 No payouts found with status '{options['status']}'")
                )
                return

            self.stdout.write(f"📋 Found {payouts.count()} payouts to process")

            for payout in payouts:
                self._process_single_payout(payout, options['dry_run'])

        self.stdout.write(
            self.style.SUCCESS('✅ Payout processing completed')
        )

    def _process_single_payout(self, payout, dry_run=False):
        """Process a single payout request"""
        
        self.stdout.write(f"\n--- Processing Payout #{payout.id} ---")
        self.stdout.write(f"User: {payout.user.email}")
        self.stdout.write(f"Amount: ${payout.amount}")
        self.stdout.write(f"Method: {payout.get_payout_method_display()}")
        self.stdout.write(f"Status: {payout.status}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("🔍 DRY RUN - Would process this payout")
            )
            return

        try:
            if payout.status == 'pending':
                # Auto-approve for testing
                payout.approve(payout.user, 'Auto-approved by management command')
                self.stdout.write("✅ Auto-approved payout")

            if payout.status == 'approved':
                # Process the payout
                result = PayoutProcessor.process_approved_payout(payout)
                
                if result['success']:
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ SUCCESS: {result['external_transaction_id']}")
                    )
                    self.stdout.write(f"   Net Amount: ${result['net_amount']}")
                    self.stdout.write(f"   Processing Fee: ${result['processing_fee']}")
                    
                    # Refresh payout status
                    payout.refresh_from_db()
                    self.stdout.write(f"   Final Status: {payout.status}")
                
                else:
                    self.stdout.write(
                        self.style.ERROR(f"❌ FAILED: {result['error_message']}")
                    )
                    if result.get('can_retry'):
                        self.stdout.write("   💡 This payout can be retried")
            
            else:
                self.stdout.write(
                    self.style.WARNING(f"⚠️ Cannot process payout with status '{payout.status}'")
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"💥 Error processing payout: {str(e)}")
            )

    def _show_summary(self):
        """Show summary statistics"""
        stats = {
            'pending': PayoutRequest.objects.filter(status='pending').count(),
            'approved': PayoutRequest.objects.filter(status='approved').count(),
            'processing': PayoutRequest.objects.filter(status='processing').count(),
            'completed': PayoutRequest.objects.filter(status='completed').count(),
            'failed': PayoutRequest.objects.filter(status='failed').count(),
        }

        total = sum(stats.values())
        
        self.stdout.write(f"\n📊 Payout Summary:")
        for status, count in stats.items():
            percentage = (count / total * 100) if total > 0 else 0
            self.stdout.write(f"   {status.title()}: {count} ({percentage:.1f}%)")
        
        if total > 0:
            success_rate = (stats['completed'] / total * 100)
            self.stdout.write(f"\n✨ Overall Success Rate: {success_rate:.1f}%") 