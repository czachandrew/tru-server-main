from django_q.tasks import async_task, schedule
from django_q.models import Schedule
from products.models import Product, Manufacturer
from vendors.models import Vendor
from offers.models import Offer

def process_batch(batch_data):
    """Process a batch of product data"""
    for item in batch_data:
        # Get or create manufacturer
        manufacturer, _ = Manufacturer.objects.get_or_create(
            name=item['manufacturer'],
            defaults={'slug': item['manufacturer'].lower().replace(' ', '-')}
        )
        
        # Get or create product
        product, created = Product.objects.get_or_create(
            part_number=item['mfr_part'],
            manufacturer=manufacturer,
            defaults={
                'name': item['name'],
                'slug': item['mfr_part'].lower().replace(' ', '-'),
                'description': item.get('description', ''),
                'specifications': {},
                'weight': item.get('product_weight'),
                'dimensions': {
                    'length': item.get('product_length'),
                    'width': item.get('product_width'),
                    'height': item.get('product_height')
                }
            }
        )
        
        # If product exists, update fields that might have changed
        if not created:
            product.name = item['name']
            product.description = item.get('description', '')
            product.save()
        
        # Get vendor (assuming Synnex in this example)
        vendor, _ = Vendor.objects.get_or_create(
            code='synnex',
            defaults={'name': 'Synnex'}
        )
        
        # Create or update offer
        offer, _ = Offer.objects.update_or_create(
            product=product,
            vendor=vendor,
            defaults={
                'cost_price': item.get('initial_price', 0),
                'selling_price': float(item.get('initial_price', 0)) * 1.15,  # Example markup
                'msrp': item.get('msrp'),
                'vendor_sku': item.get('reseller_part', ''),
                'stock_quantity': item.get('qty', 0)
            }
        )
    
    return f"Processed {len(batch_data)} items"