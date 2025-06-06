from django.core.management.base import BaseCommand
from django.utils.text import slugify
from products.models import Product, Manufacturer, Category, ProductCategory


class Command(BaseCommand):
    help = 'Create demo products for presentations and testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing demo products before creating new ones',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=20,
            help='Number of demo products to create (default: 20)',
        )

    def handle(self, *args, **options):
        if options['clear_existing']:
            deleted_count = Product.objects.filter(is_demo=True).count()
            Product.objects.filter(is_demo=True).delete()
            self.stdout.write(
                self.style.WARNING(f'Deleted {deleted_count} existing demo products')
            )

        # Create or get manufacturers - use existing ones where possible
        try:
            apple = Manufacturer.objects.get(name="Apple")
        except Manufacturer.DoesNotExist:
            try:
                apple = Manufacturer.objects.get(slug__icontains="apple")
            except Manufacturer.DoesNotExist:
                apple = Manufacturer.objects.create(
                    name="Apple", 
                    slug='apple-demo',
                    website='https://www.apple.com',
                    description='American multinational technology company'
                )
        
        try:
            dell = Manufacturer.objects.get(name="Dell")
        except Manufacturer.DoesNotExist:
            dell = Manufacturer.objects.create(
                name="Dell",
                slug='dell-demo',
                website='https://www.dell.com',
                description='American multinational computer technology company'
            )
        
        try:
            hp = Manufacturer.objects.get(name="HP")
        except Manufacturer.DoesNotExist:
            hp = Manufacturer.objects.create(
                name="HP",
                slug='hp-demo',
                website='https://www.hp.com',
                description='American multinational information technology company'
            )
        
        try:
            logitech = Manufacturer.objects.get(name="Logitech")
        except Manufacturer.DoesNotExist:
            try:
                logitech = Manufacturer.objects.get(slug="logitech")
            except Manufacturer.DoesNotExist:
                logitech = Manufacturer.objects.create(
                    name="Logitech",
                    slug='logitech-demo',
                    website='https://www.logitech.com',
                    description='Swiss computer peripherals and software company'
                )

        # Create or get categories
        try:
            laptops_cat, _ = Category.objects.get_or_create(
                name="Laptops",
                defaults={'slug': 'laptops', 'description': 'Portable computers'}
            )
        except Exception:
            laptops_cat = Category.objects.get(name="Laptops")
        
        try:
            accessories_cat, _ = Category.objects.get_or_create(
                name="Computer Accessories",
                defaults={'slug': 'computer-accessories', 'description': 'Computer peripherals and accessories'}
            )
        except Exception:
            accessories_cat = Category.objects.get(name="Computer Accessories")

        # Demo products that are likely to be searched for
        demo_products = [
            {
                'name': 'MacBook Pro 13-inch',
                'manufacturer': apple,
                'part_number': 'MBP13-2023',
                'description': 'Apple MacBook Pro 13-inch with M2 chip, perfect for professional workflows',
                'categories': [laptops_cat],
                'specifications': {
                    'processor': 'Apple M2',
                    'memory': '8GB',
                    'storage': '256GB SSD',
                    'screen_size': '13.3 inches',
                    'weight': '3.0 lbs'
                }
            },
            {
                'name': 'MacBook Air 13-inch',
                'manufacturer': apple,
                'part_number': 'MBA13-2023',
                'description': 'Ultra-thin and lightweight MacBook Air with M2 chip',
                'categories': [laptops_cat],
                'specifications': {
                    'processor': 'Apple M2',
                    'memory': '8GB',
                    'storage': '256GB SSD',
                    'screen_size': '13.6 inches',
                    'weight': '2.7 lbs'
                }
            },
            {
                'name': 'Dell XPS 13',
                'manufacturer': dell,
                'part_number': 'XPS13-9320',
                'description': 'Premium Dell XPS 13 ultrabook with Intel processors',
                'categories': [laptops_cat],
                'specifications': {
                    'processor': 'Intel Core i7',
                    'memory': '16GB',
                    'storage': '512GB SSD',
                    'screen_size': '13.4 inches',
                    'weight': '2.6 lbs'
                }
            },
            {
                'name': 'Dell Latitude 7420',
                'manufacturer': dell,
                'part_number': 'LAT7420',
                'description': 'Business-class Dell Latitude laptop for professionals',
                'categories': [laptops_cat],
                'specifications': {
                    'processor': 'Intel Core i5',
                    'memory': '8GB',
                    'storage': '256GB SSD',
                    'screen_size': '14 inches',
                    'weight': '3.1 lbs'
                }
            },
            {
                'name': 'HP EliteBook 840',
                'manufacturer': hp,
                'part_number': 'EB840-G9',
                'description': 'HP EliteBook 840 G9 business laptop with security features',
                'categories': [laptops_cat],
                'specifications': {
                    'processor': 'Intel Core i5',
                    'memory': '16GB',
                    'storage': '512GB SSD',
                    'screen_size': '14 inches',
                    'weight': '3.2 lbs'
                }
            },
            {
                'name': 'HP Pavilion 15',
                'manufacturer': hp,
                'part_number': 'PAV15-2023',
                'description': 'Affordable HP Pavilion 15 laptop for everyday computing',
                'categories': [laptops_cat],
                'specifications': {
                    'processor': 'AMD Ryzen 5',
                    'memory': '8GB',
                    'storage': '256GB SSD',
                    'screen_size': '15.6 inches',
                    'weight': '3.9 lbs'
                }
            },
            {
                'name': 'Logitech MX Master 3',
                'manufacturer': logitech,
                'part_number': 'MX-MASTER-3',
                'description': 'Advanced wireless mouse for power users and creatives',
                'categories': [accessories_cat],
                'specifications': {
                    'connectivity': 'Wireless',
                    'battery_life': '70 days',
                    'dpi': '4000',
                    'buttons': '7',
                    'weight': '141g'
                }
            },
            {
                'name': 'Logitech MX Keys',
                'manufacturer': logitech,
                'part_number': 'MX-KEYS',
                'description': 'Wireless illuminated keyboard for productivity',
                'categories': [accessories_cat],
                'specifications': {
                    'connectivity': 'Wireless',
                    'battery_life': '10 days with backlight',
                    'layout': 'Full-size',
                    'backlight': 'Yes',
                    'weight': '810g'
                }
            },
            # Add more common search terms
            {
                'name': 'Dell Monitor 27 inch',
                'manufacturer': dell,
                'part_number': 'S2722DC',
                'description': '27-inch Dell USB-C monitor with 4K resolution',
                'categories': [accessories_cat],
                'specifications': {
                    'screen_size': '27 inches',
                    'resolution': '3840 x 2160',
                    'connectivity': 'USB-C, HDMI',
                    'refresh_rate': '60Hz'
                }
            },
            {
                'name': 'Apple Magic Mouse',
                'manufacturer': apple,
                'part_number': 'MAGIC-MOUSE-2',
                'description': 'Apple Magic Mouse with multi-touch surface',
                'categories': [accessories_cat],
                'specifications': {
                    'connectivity': 'Wireless',
                    'battery_life': '1 month',
                    'features': 'Multi-touch surface',
                    'weight': '99g'
                }
            }
        ]

        created_count = 0
        for product_data in demo_products[:options['count']]:
            # Create slug from name
            slug = slugify(product_data['name'])
            
            # Check if product already exists
            if Product.objects.filter(
                manufacturer=product_data['manufacturer'],
                part_number=product_data['part_number']
            ).exists():
                self.stdout.write(
                    self.style.WARNING(
                        f'Product {product_data["name"]} already exists, skipping...'
                    )
                )
                continue
            
            # Extract categories from product data
            categories = product_data.pop('categories', [])
            
            # Create the product
            product = Product.objects.create(
                slug=slug,
                is_demo=True,
                source='manual',
                status='active',
                **product_data
            )
            
            # Add categories
            for category in categories:
                ProductCategory.objects.create(
                    product=product,
                    category=category,
                    is_primary=True
                )
            
            created_count += 1
            self.stdout.write(
                self.style.SUCCESS(f'Created demo product: {product.name}')
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSuccessfully created {created_count} demo products!'
            )
        ) 