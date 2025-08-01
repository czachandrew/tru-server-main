#!/usr/bin/env python
"""
Interactive Django Shell Script for Referral System Testing
Run this to test the system interactively in Django shell
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_platform.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from users.models import User, ReferralCode, Promotion, UserReferralCode, ReferralDisbursement
from users.services import ReferralCodeService, OrganizationService
from affiliates.models import AffiliateLink, AffiliateClickEvent, PurchaseIntentEvent
from products.models import Product, Manufacturer
from vendors.models import Vendor
from offers.models import Offer

def print_help():
    print("""
🧪 Interactive Referral System Test Commands:

1. create_test_data() - Create test organization, user, and product
2. test_add_code() - Add referral code to user
3. test_purchase() - Simulate a purchase
4. test_summaries() - Get user and organization summaries
5. test_validation() - Test code validation
6. cleanup_data() - Clean up all test data
7. show_data() - Show current test data
8. help() - Show this help

Example workflow:
    create_test_data()
    test_add_code()
    test_purchase()
    test_summaries()
    cleanup_data()
""")

# Global test data storage
test_data = {}

def create_test_data():
    """Create test data for manual testing"""
    global test_data
    
    print("📝 Creating test data...")
    
    # Create organization
    org_user = User.objects.create_user(
        email='shell-test-church@example.com',
        password='testpass123'
    )
    org_user.profile.is_organization = True
    org_user.profile.organization_name = 'Shell Test Church'
    org_user.profile.organization_type = 'church'
    org_user.profile.save()
    print(f"✅ Created organization: {org_user.profile.organization_name}")
    
    # Create regular user
    user = User.objects.create_user(
        email='shell-test-user@example.com',
        password='testpass123'
    )
    print(f"✅ Created user: {user.email}")
    
    # Create product infrastructure
    manufacturer = Manufacturer.objects.create(
        name='Shell Test Manufacturer',
        slug='shell-test-manufacturer'
    )
    
    vendor = Vendor.objects.create(
        name='Shell Test Vendor',
        slug='shell-test-vendor',
        code='SHELLTEST'
    )
    
    product = Product.objects.create(
        name='Shell Test Product',
        part_number='SHELL123',
        manufacturer=manufacturer,
        description='A test product for shell testing'
    )
    
    offer = Offer.objects.create(
        product=product,
        vendor=vendor,
        selling_price=Decimal('299.99'),
        commission_rate=Decimal('10.00'),  # 10% commission
        is_active=True
    )
    
    affiliate_link = AffiliateLink.objects.create(
        product=product,
        platform='amazon',
        platform_id='B00SHELL123',
        original_url='https://amazon.com/shell-test-product',
        affiliate_url='https://amazon.com/shell-test-product?ref=shell',
        commission_rate=Decimal('10.00')
    )
    
    # Create referral code and promotion
    referral_code = ReferralCode.create_for_organization(org_user)
    
    promotion = Promotion.objects.create(
        organization=org_user,
        referral_code=referral_code,
        start_date=timezone.now() - timedelta(days=3),  # Started 3 days ago
        is_active=True
    )
    
    test_data = {
        'org_user': org_user,
        'user': user,
        'product': product,
        'offer': offer,
        'affiliate_link': affiliate_link,
        'referral_code': referral_code,
        'promotion': promotion,
        'manufacturer': manufacturer,
        'vendor': vendor
    }
    
    print(f"✅ Created referral code: {referral_code.code}")
    print(f"✅ Created product: {product.name} (${offer.selling_price})")
    print("✅ Test data created successfully!")
    
    return test_data

def test_add_code():
    """Test adding referral code to user"""
    global test_data
    
    if not test_data:
        print("❌ No test data found. Run create_test_data() first.")
        return
    
    user = test_data['user']
    referral_code = test_data['referral_code']
    
    print(f"📋 Adding referral code {referral_code.code} to user {user.email}...")
    
    try:
        user_code = ReferralCodeService.add_user_referral_code(user, referral_code.code)
        print(f"✅ Added code successfully!")
        
        # Check allocations
        allocations = ReferralCodeService.calculate_user_allocations(user)
        print(f"📊 Allocations: User {allocations['user']}%, Codes {len(allocations['codes'])} codes")
        
        return user_code
    except Exception as e:
        print(f"❌ Failed to add code: {e}")
        return None

def test_purchase():
    """Test simulating a purchase"""
    global test_data
    
    if not test_data:
        print("❌ No test data found. Run create_test_data() first.")
        return
    
    user = test_data['user']
    affiliate_link = test_data['affiliate_link']
    
    print(f"📋 Simulating purchase for user {user.email}...")
    
    try:
        # Create click event
        click_event = AffiliateClickEvent.objects.create(
            user=user,
            affiliate_link=affiliate_link,
            session_id='shell-test-session-123',
            target_domain='amazon.com',
            product_data={'name': 'Shell Test Product', 'price': '299.99'}
        )
        
        # Create purchase intent
        purchase_intent = PurchaseIntentEvent.objects.create(
            click_event=click_event,
            intent_stage='cart_view',
            confidence_level='HIGH',
            confidence_score=Decimal('0.95'),
            cart_total=Decimal('299.99'),
            cart_items=[{'name': 'Shell Test Product', 'price': '299.99'}],
            matched_products=[{'name': 'Shell Test Product', 'price': '299.99'}],
            page_url='https://amazon.com/cart',
            page_title='Shopping Cart'
        )
        
        # Create projected earning
        transaction = purchase_intent.create_projected_earning()
        
        if transaction:
            print(f"✅ Created projected earning: ${transaction.amount}")
            
            # Check disbursements
            disbursements = ReferralDisbursement.objects.filter(
                wallet_transaction=transaction
            )
            print(f"📊 Created {disbursements.count()} disbursements")
            
            for disbursement in disbursements:
                print(f"  💰 ${disbursement.amount} to {disbursement.recipient_user.email}")
            
            return transaction
        else:
            print("❌ Failed to create projected earning")
            return None
            
    except Exception as e:
        print(f"❌ Failed to simulate purchase: {e}")
        return None

def test_summaries():
    """Test getting user and organization summaries"""
    global test_data
    
    if not test_data:
        print("❌ No test data found. Run create_test_data() first.")
        return
    
    user = test_data['user']
    org_user = test_data['org_user']
    
    print("📋 Getting user referral summary...")
    try:
        summary = ReferralCodeService.get_user_referral_summary(user)
        print(f"📊 Total giving: ${summary['total_giving']}")
        print(f"📊 Potential giving: ${summary['potential_giving']}")
        print(f"📊 Net earnings: ${summary['net_earnings']}")
        print(f"📊 User allocation: {summary['user_allocation_percentage']}%")
    except Exception as e:
        print(f"❌ Failed to get user summary: {e}")
    
    print("\n📋 Getting organization summary...")
    try:
        org_summary = OrganizationService.get_organization_summary(org_user)
        print(f"📊 Active promotions: {len(org_summary['active_promotions'])}")
        print(f"📊 Total received: ${org_summary['total_received']}")
        print(f"📊 Pending disbursements: ${org_summary['pending_disbursements']}")
    except Exception as e:
        print(f"❌ Failed to get org summary: {e}")

def test_validation():
    """Test code validation"""
    global test_data
    
    if not test_data:
        print("❌ No test data found. Run create_test_data() first.")
        return
    
    referral_code = test_data['referral_code']
    
    print("📋 Testing code validation...")
    
    # Test valid code
    is_valid, result = ReferralCodeService.validate_referral_code(referral_code.code)
    if is_valid:
        print(f"✅ Code {referral_code.code} is valid")
    else:
        print(f"❌ Code validation failed: {result}")
    
    # Test invalid code
    is_valid, result = ReferralCodeService.validate_referral_code('INVALID')
    if not is_valid:
        print(f"✅ Invalid code correctly rejected: {result}")
    else:
        print("❌ Invalid code should have been rejected")

def show_data():
    """Show current test data"""
    global test_data
    
    if not test_data:
        print("❌ No test data found. Run create_test_data() first.")
        return
    
    print("📋 Current test data:")
    print(f"  Organization: {test_data['org_user'].profile.organization_name}")
    print(f"  User: {test_data['user'].email}")
    print(f"  Product: {test_data['product'].name}")
    print(f"  Referral Code: {test_data['referral_code'].code}")
    print(f"  Promotion Status: {test_data['promotion'].get_status_display()}")

def cleanup_data():
    """Clean up test data"""
    global test_data
    
    if not test_data:
        print("❌ No test data found.")
        return
    
    print("🧹 Cleaning up test data...")
    
    try:
        # Delete in reverse order to avoid foreign key constraints
        ReferralDisbursement.objects.filter(
            wallet_transaction__user=test_data['user']
        ).delete()
        
        PurchaseIntentEvent.objects.filter(
            click_event__user=test_data['user']
        ).delete()
        
        AffiliateClickEvent.objects.filter(user=test_data['user']).delete()
        
        UserReferralCode.objects.filter(user=test_data['user']).delete()
        
        Promotion.objects.filter(organization=test_data['org_user']).delete()
        ReferralCode.objects.filter(owner=test_data['org_user']).delete()
        
        AffiliateLink.objects.filter(product=test_data['product']).delete()
        test_data['offer'].delete()
        test_data['product'].delete()
        test_data['vendor'].delete()
        test_data['manufacturer'].delete()
        
        test_data['user'].delete()
        test_data['org_user'].delete()
        
        test_data = {}
        print("✅ Test data cleaned up successfully")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

# Print help on startup
print_help() 