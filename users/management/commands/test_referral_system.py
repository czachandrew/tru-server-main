from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from users.models import User, ReferralCode, Promotion, UserReferralCode, ReferralDisbursement
from users.services import ReferralCodeService, OrganizationService
from affiliates.models import AffiliateLink, AffiliateClickEvent, PurchaseIntentEvent
from products.models import Product, Manufacturer
import random
import string


class Command(BaseCommand):
    help = 'Test the referral code system with sample data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up test data after running',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== 🧪 Testing Referral Code System ==='))
        
        # Create test data
        self.create_test_data()
        
        # Test the system
        self.test_referral_system()
        
        # Cleanup if requested
        if options['cleanup']:
            self.cleanup_test_data()
        
        self.stdout.write(self.style.SUCCESS('✅ Referral system test completed!'))

    def create_test_data(self):
        """Create test organizations, users, and products"""
        self.stdout.write('📝 Creating test data...')
        
        # Generate unique emails
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        org_email = f'test-church-{random_suffix}@example.com'
        user_email = f'test-user-{random_suffix}@example.com'
        
        # Create organization
        self.org_user = User.objects.create_user(
            email=org_email,
            password='testpass123'
        )
        self.org_user.profile.is_organization = True
        self.org_user.profile.organization_name = f'Test Church {random_suffix}'
        self.org_user.profile.organization_type = 'church'
        self.org_user.profile.save()
        
        # Create regular user
        self.user = User.objects.create_user(
            email=user_email,
            password='testpass123'
        )
        
        # Create manufacturer, vendor, and product (with unique names)
        # Generate unique names
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        manufacturer_name = f'Test Manufacturer {random_suffix}'
        vendor_name = f'Test Vendor {random_suffix}'
        product_name = f'Test Product {random_suffix}'
        
        self.manufacturer = Manufacturer.objects.create(
            name=manufacturer_name,
            slug=f'test-manufacturer-{random_suffix.lower()}'
        )
        
        from vendors.models import Vendor
        self.vendor = Vendor.objects.create(
            name=vendor_name,
            slug=f'test-vendor-{random_suffix.lower()}',
            code=f'TEST{random_suffix}'
        )
        
        self.product = Product.objects.create(
            name=product_name,
            part_number=f'TEST123{random_suffix}',
            manufacturer=self.manufacturer,
            description='A test product for referral system testing'
        )
        
        # Create offer for the product
        from offers.models import Offer
        self.offer = Offer.objects.create(
            product=self.product,
            vendor=self.vendor,
            selling_price=Decimal('99.99'),
            commission_rate=Decimal('5.00'),  # 5% commission
            is_active=True
        )
        
        # Create affiliate link
        self.affiliate_link = AffiliateLink.objects.create(
            product=self.product,
            platform='amazon',
            platform_id='B00TEST123',
            original_url='https://amazon.com/test-product',
            affiliate_url='https://amazon.com/test-product?ref=test',
            commission_rate=Decimal('5.00')  # 5% commission
        )
        
        # Create referral code and promotion
        self.referral_code = ReferralCode.create_for_organization(self.org_user)
        
        self.promotion = Promotion.objects.create(
            organization=self.org_user,
            referral_code=self.referral_code,
            start_date=timezone.now() - timedelta(days=7),  # Started 7 days ago
            is_active=True
        )
        
        self.stdout.write(f'✅ Created test data: {self.org_user.profile.organization_name}, {self.user.email}')

    def test_referral_system(self):
        """Test the referral system functionality"""
        self.stdout.write('🧪 Testing referral system...')
        
        # Test 1: Add referral code to user
        self.stdout.write('  📋 Test 1: Adding referral code to user...')
        try:
            user_code = ReferralCodeService.add_user_referral_code(
                self.user, 
                self.referral_code.code
            )
            self.stdout.write(f'    ✅ Added code {self.referral_code.code} to user')
            
            # Check allocations
            allocations = ReferralCodeService.calculate_user_allocations(self.user)
            self.stdout.write(f'    📊 Allocations: User {allocations["user"]}%, Codes {len(allocations["codes"])} codes')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    ❌ Failed to add code: {e}'))
            return
        
        # Test 2: Simulate purchase intent
        self.stdout.write('  📋 Test 2: Simulating purchase intent...')
        try:
            # Create click event
            click_event = AffiliateClickEvent.objects.create(
                user=self.user,
                affiliate_link=self.affiliate_link,
                session_id='test-session-123',
                target_domain='amazon.com',
                product_data={'name': 'Test Product', 'price': '99.99'}
            )
            
            # Create purchase intent
            purchase_intent = PurchaseIntentEvent.objects.create(
                click_event=click_event,
                intent_stage='cart_view',
                confidence_level='HIGH',
                confidence_score=Decimal('0.85'),
                cart_total=Decimal('99.99'),
                cart_items=[{'name': 'Test Product', 'price': '99.99'}],
                matched_products=[{'name': 'Test Product', 'price': '99.99'}],
                page_url='https://amazon.com/cart',
                page_title='Shopping Cart'
            )
            
            # Create projected earning (this should also create disbursements)
            transaction = purchase_intent.create_projected_earning()
            
            if transaction:
                self.stdout.write(f'    ✅ Created projected earning: ${transaction.amount}')
                
                # Check disbursements
                disbursements = ReferralDisbursement.objects.filter(
                    wallet_transaction=transaction
                )
                self.stdout.write(f'    📊 Created {disbursements.count()} disbursements')
                
                for disbursement in disbursements:
                    self.stdout.write(f'      💰 ${disbursement.amount} to {disbursement.recipient_user.email}')
            else:
                self.stdout.write('    ❌ Failed to create projected earning')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    ❌ Failed to simulate purchase: {e}'))
        
        # Test 3: Get user summary
        self.stdout.write('  📋 Test 3: Getting user referral summary...')
        try:
            summary = ReferralCodeService.get_user_referral_summary(self.user)
            self.stdout.write(f'    📊 Total giving: ${summary["total_giving"]}')
            self.stdout.write(f'    📊 Potential giving: ${summary["potential_giving"]}')
            self.stdout.write(f'    📊 Net earnings: ${summary["net_earnings"]}')
            self.stdout.write(f'    📊 User allocation: {summary["user_allocation_percentage"]}%')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    ❌ Failed to get summary: {e}'))
        
        # Test 4: Get organization summary
        self.stdout.write('  📋 Test 4: Getting organization summary...')
        try:
            org_summary = OrganizationService.get_organization_summary(self.org_user)
            self.stdout.write(f'    📊 Active promotions: {len(org_summary["active_promotions"])}')
            self.stdout.write(f'    📊 Total received: ${org_summary["total_received"]}')
            self.stdout.write(f'    📊 Pending disbursements: ${org_summary["pending_disbursements"]}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    ❌ Failed to get org summary: {e}'))
        
        # Test 5: Test code validation
        self.stdout.write('  📋 Test 5: Testing code validation...')
        try:
            is_valid, result = ReferralCodeService.validate_referral_code(self.referral_code.code)
            if is_valid:
                self.stdout.write(f'    ✅ Code {self.referral_code.code} is valid')
            else:
                self.stdout.write(f'    ❌ Code validation failed: {result}')
                
            # Test invalid code
            is_valid, result = ReferralCodeService.validate_referral_code('INVALID')
            if not is_valid:
                self.stdout.write(f'    ✅ Invalid code correctly rejected: {result}')
            else:
                self.stdout.write('    ❌ Invalid code should have been rejected')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    ❌ Failed to validate code: {e}'))

    def cleanup_test_data(self):
        """Clean up test data"""
        self.stdout.write('🧹 Cleaning up test data...')
        
        # Delete in reverse order to avoid foreign key constraints
        ReferralDisbursement.objects.filter(
            wallet_transaction__user=self.user
        ).delete()
        
        PurchaseIntentEvent.objects.filter(
            click_event__user=self.user
        ).delete()
        
        AffiliateClickEvent.objects.filter(user=self.user).delete()
        
        UserReferralCode.objects.filter(user=self.user).delete()
        
        Promotion.objects.filter(organization=self.org_user).delete()
        ReferralCode.objects.filter(owner=self.org_user).delete()
        
        AffiliateLink.objects.filter(product=self.product).delete()
        self.offer.delete()
        self.product.delete()
        self.vendor.delete()
        self.manufacturer.delete()
        
        self.user.delete()
        self.org_user.delete()
        
        self.stdout.write('✅ Test data cleaned up') 