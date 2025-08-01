#!/usr/bin/env python
"""
Manual Test Script for Referral System
Run this to test the complete workflow manually
"""

import os
import sys
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_platform.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from users.models import User, ReferralCode, Promotion, UserReferralCode, ReferralDisbursement
from users.services import ReferralCodeService, OrganizationService
from affiliates.models import AffiliateLink, AffiliateClickEvent, PurchaseIntentEvent
from products.models import Product, Manufacturer
from vendors.models import Vendor
from offers.models import Offer

def print_header(title):
    print(f"\n{'='*50}")
    print(f"🧪 {title}")
    print(f"{'='*50}")

def print_step(step, description):
    print(f"\n📋 Step {step}: {description}")
    print("-" * 40)

def create_test_data():
    """Create test data for manual testing"""
    print_header("Creating Test Data")
    
    # Create organization
    org_user = User.objects.create_user(
        email='manual-test-church@example.com',
        password='testpass123'
    )
    org_user.profile.is_organization = True
    org_user.profile.organization_name = 'Manual Test Church'
    org_user.profile.organization_type = 'church'
    org_user.profile.save()
    print(f"✅ Created organization: {org_user.profile.organization_name}")
    
    # Create regular user
    user = User.objects.create_user(
        email='manual-test-user@example.com',
        password='testpass123'
    )
    print(f"✅ Created user: {user.email}")
    
    # Create product infrastructure
    manufacturer = Manufacturer.objects.create(
        name='Manual Test Manufacturer',
        slug='manual-test-manufacturer'
    )
    
    vendor = Vendor.objects.create(
        name='Manual Test Vendor',
        slug='manual-test-vendor',
        code='MANUALTEST'
    )
    
    product = Product.objects.create(
        name='Manual Test Product',
        part_number='MANUAL123',
        manufacturer=manufacturer,
        description='A test product for manual testing'
    )
    
    offer = Offer.objects.create(
        product=product,
        vendor=vendor,
        selling_price=Decimal('199.99'),
        commission_rate=Decimal('8.00'),  # 8% commission
        is_active=True
    )
    
    affiliate_link = AffiliateLink.objects.create(
        product=product,
        platform='amazon',
        platform_id='B00MANUAL123',
        original_url='https://amazon.com/manual-test-product',
        affiliate_url='https://amazon.com/manual-test-product?ref=manual',
        commission_rate=Decimal('8.00')
    )
    
    print(f"✅ Created product: {product.name} (${offer.selling_price})")
    
    # Create referral code and promotion
    referral_code = ReferralCode.create_for_organization(org_user)
    
    promotion = Promotion.objects.create(
        organization=org_user,
        referral_code=referral_code,
        start_date=timezone.now() - timedelta(days=5),  # Started 5 days ago
        is_active=True
    )
    
    print(f"✅ Created referral code: {referral_code.code}")
    print(f"✅ Created promotion: {promotion.get_status_display()}")
    
    return {
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

def test_referral_workflow(test_data):
    """Test the complete referral workflow"""
    print_header("Testing Referral Workflow")
    
    org_user = test_data['org_user']
    user = test_data['user']
    affiliate_link = test_data['affiliate_link']
    referral_code = test_data['referral_code']
    
    # Step 1: Add referral code to user
    print_step(1, "Adding referral code to user")
    try:
        user_code = ReferralCodeService.add_user_referral_code(user, referral_code.code)
        print(f"✅ Added code {referral_code.code} to user")
        
        # Check allocations
        allocations = ReferralCodeService.calculate_user_allocations(user)
        print(f"📊 Allocations: User {allocations['user']}%, Codes {len(allocations['codes'])} codes")
        
    except Exception as e:
        print(f"❌ Failed to add code: {e}")
        return False
    
    # Step 2: Simulate purchase intent
    print_step(2, "Simulating purchase intent")
    try:
        # Create click event
        click_event = AffiliateClickEvent.objects.create(
            user=user,
            affiliate_link=affiliate_link,
            session_id='manual-test-session-123',
            target_domain='amazon.com',
            product_data={'name': 'Manual Test Product', 'price': '199.99'}
        )
        
        # Create purchase intent
        purchase_intent = PurchaseIntentEvent.objects.create(
            click_event=click_event,
            intent_stage='cart_view',
            confidence_level='HIGH',
            confidence_score=Decimal('0.90'),
            cart_total=Decimal('199.99'),
            cart_items=[{'name': 'Manual Test Product', 'price': '199.99'}],
            matched_products=[{'name': 'Manual Test Product', 'price': '199.99'}],
            page_url='https://amazon.com/cart',
            page_title='Shopping Cart'
        )
        
        # Create projected earning (this should also create disbursements)
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
        else:
            print("❌ Failed to create projected earning")
            return False
            
    except Exception as e:
        print(f"❌ Failed to simulate purchase: {e}")
        return False
    
    # Step 3: Get user summary
    print_step(3, "Getting user referral summary")
    try:
        summary = ReferralCodeService.get_user_referral_summary(user)
        print(f"📊 Total giving: ${summary['total_giving']}")
        print(f"📊 Potential giving: ${summary['potential_giving']}")
        print(f"📊 Net earnings: ${summary['net_earnings']}")
        print(f"📊 User allocation: {summary['user_allocation_percentage']}%")
        
    except Exception as e:
        print(f"❌ Failed to get summary: {e}")
        return False
    
    # Step 4: Get organization summary
    print_step(4, "Getting organization summary")
    try:
        org_summary = OrganizationService.get_organization_summary(org_user)
        print(f"📊 Active promotions: {len(org_summary['active_promotions'])}")
        print(f"📊 Total received: ${org_summary['total_received']}")
        print(f"📊 Pending disbursements: ${org_summary['pending_disbursements']}")
        
    except Exception as e:
        print(f"❌ Failed to get org summary: {e}")
        return False
    
    # Step 5: Test code validation
    print_step(5, "Testing code validation")
    try:
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
            
    except Exception as e:
        print(f"❌ Failed to validate code: {e}")
        return False
    
    return True

def cleanup_test_data(test_data):
    """Clean up test data"""
    print_header("Cleaning Up Test Data")
    
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
        
        print("✅ Test data cleaned up successfully")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

def main():
    """Main test function"""
    print_header("Manual Referral System Test")
    print("This script will create test data, run the workflow, and clean up.")
    
    # Create test data
    test_data = create_test_data()
    
    # Test the workflow
    success = test_referral_workflow(test_data)
    
    if success:
        print_header("✅ Test Completed Successfully!")
        print("All referral system features are working correctly.")
    else:
        print_header("❌ Test Failed")
        print("There were issues with the referral system.")
    
    # Ask user if they want to clean up
    response = input("\n🧹 Do you want to clean up the test data? (y/n): ").lower().strip()
    if response in ['y', 'yes']:
        cleanup_test_data(test_data)
    else:
        print("📝 Test data left in database for manual inspection.")
        print("You can run this script again with cleanup later.")

if __name__ == "__main__":
    main() 