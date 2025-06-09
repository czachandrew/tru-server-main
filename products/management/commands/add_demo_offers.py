from django.core.management.base import BaseCommand
from products.models import Product
from offers.models import Offer
from vendors.models import Vendor
from decimal import Decimal


class Command(BaseCommand):
    help = 'Add offers to demo products so they appear in Chrome extension'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔧 Adding offers to demo products...'))
        
        # Get demo products
        demo_products = Product.objects.filter(is_demo=True)
        self.stdout.write(f'Found {demo_products.count()} demo products')
        
        # Get or create a demo vendor
        demo_vendor, created = Vendor.objects.get_or_create(
            name='TruPrice Demo Vendor',
            defaults={
                'code': 'DEMO',
                'contact_name': 'Demo Manager',
                'contact_email': 'demo@trueprice.com',
                'contact_phone': '555-0123'
            }
        )
        
        if created:
            self.stdout.write(f'Created demo vendor: {demo_vendor.name}')
        else:
            self.stdout.write(f'Using existing demo vendor: {demo_vendor.name}')
        
        offers_created = 0
        
        # Add offers to each demo product
        for product in demo_products:
            # Check if product already has offers
            existing_offers = Offer.objects.filter(product=product).count()
            if existing_offers > 0:
                self.stdout.write(f'{product.name} already has {existing_offers} offers')
                continue
            
            # Set prices based on product type
            if 'macbook pro' in product.name.lower():
                selling_price = Decimal('1299.99')
                cost_price = Decimal('1199.99')
            elif 'macbook air' in product.name.lower():
                selling_price = Decimal('999.99')
                cost_price = Decimal('899.99')
            elif 'dell' in product.name.lower():
                selling_price = Decimal('899.99')
                cost_price = Decimal('799.99')
            elif 'hp' in product.name.lower():
                selling_price = Decimal('799.99')
                cost_price = Decimal('699.99')
            elif 'lenovo' in product.name.lower():
                selling_price = Decimal('749.99')
                cost_price = Decimal('649.99')
            else:
                selling_price = Decimal('699.99')
                cost_price = Decimal('599.99')
            
            # Create offer
            offer = Offer.objects.create(
                product=product,
                vendor=demo_vendor,
                cost_price=cost_price,
                selling_price=selling_price,
                stock_quantity=10,
                is_in_stock=True,
                vendor_sku=f'DEMO-{product.part_number}'
            )
            
            self.stdout.write(f'✅ Created offer for {product.name}: ${selling_price}')
            offers_created += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'🎉 Successfully created {offers_created} demo offers!')
        ) 