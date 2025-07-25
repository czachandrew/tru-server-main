from django.test import TestCase
from decimal import Decimal
from users.models import User
from products.models import Product, Manufacturer
from offers.models import Offer, Vendor
from affiliates.models import AffiliateLink, AffiliateClickEvent, PurchaseIntentEvent

class TestAffiliateCommissionCalculationReplicatingProd(TestCase):
    def setUp(self):
        # 1. Create user and profile
        self.user, _ = User.objects.get_or_create(email='testuser@example.com')
        self.user.profile.activity_score = Decimal('1.00')  # 15% revenue share
        self.user.profile.save()

        # 1. Create manufacturer (required)
        self.manufacturer = Manufacturer.objects.create(
            name="OneOdio",
            # Add any other required fields here
        )

        # 2. Create vendor (for offer, if required)
        self.vendor = Vendor.objects.create(
            name="Amazon Marketplace",
            # Add any other required fields here
        )

        # 3. Create product (with manufacturer)
        self.product = Product.objects.create(
            id=39613,
            name="OneOdio Wired Headphones - Over Ear Headphones with Noise Isolation Dual Jack Professional Studio Monitor & Mixing Recording Headsets for Guitar Amp Drum Podcast Keyboard PC Computer",
            part_number="B08738D39L",
            manufacturer=self.manufacturer,
            # Add any other required fields here
        )

        # 4. Create offer (with vendor)
        self.offer = Offer.objects.create(
            id=40087,
            product=self.product,
            selling_price=Decimal('34.99'),
            vendor=self.vendor,
            is_active=True,
            is_in_stock=True,
            commission_rate=Decimal('4.00')
        )

        # 5. Create affiliate link (as before)
        self.affiliate_link = AffiliateLink.objects.create(
            id=579,
            product=self.product,
            platform='amazon',
            platform_id='B08738D39L',
            original_url='https://amzn.to/4lxLvB4',
            affiliate_url='https://amzn.to/4lxLvB4',
            commission_rate=None,
            is_active=True
        )

    def test_commission_matches_real_data(self):
        # 5. Create click event
        click_event = AffiliateClickEvent.objects.create(
            user=self.user,
            affiliate_link=self.affiliate_link,
            source='extension',
            session_id='test_session_456',
            target_domain='amazon.com',
            product_data={
                "name": self.product.name,
                "asin": "B08738D39L",
                "sku": "B08738D39L",
                "platform": "amazon"
            }
        )

        # 6. Create purchase intent event
        intent = PurchaseIntentEvent.objects.create(
            click_event=click_event,
            intent_stage='shipping_info',
            confidence_level='HIGH',
            confidence_score=Decimal('0.85'),
            cart_total=None,
            cart_items=[],
            matched_products=[],
            page_url='https://www.amazon.com/dp/B08738D39L',
            has_created_projection=False
        )
        intent.product_data = click_event.product_data

        # 7. Calculate commission
        commission = intent.calculate_projected_commission()
        print(f"Calculated commission: {commission}")

        # 8. Print out all relevant values for debugging
        print(f"Offer price: {self.offer.selling_price}")
        print(f"Offer commission rate: {self.offer.commission_rate}")
        print(f"Affiliate link commission rate: {self.affiliate_link.commission_rate}")
        print(f"User revenue share rate: {self.user.profile.revenue_share_rate}")

        # 9. Assert commission is as expected
        # Should use offer's commission rate (4%)
        expected = Decimal('34.99') * Decimal('0.04') * Decimal('0.15')
        expected = expected.quantize(Decimal('0.01'))
        self.assertEqual(commission, expected)
        self.assertNotEqual(commission, Decimal('0.00'))