# Usage: python manage.py shell < dump_affiliate_product.py
# Edit the asin variable below to debug a different product

from products.models import Product
from offers.models import Offer
from affiliates.models import AffiliateLink

asin = 'B08738D39L'  # Change this to debug a different product

print(f'--- Dumping data for ASIN: {asin} ---')
product = Product.objects.filter(part_number=asin).first()
if not product:
    print(f'Product with ASIN {asin} not found.')
    exit()

print('Product:')
print(f'  Name: {product.name}')
print(f'  ID: {product.id}')
print(f'  Part Number: {product.part_number}')

offers = Offer.objects.filter(product=product)
print(f'Offers ({offers.count()}):')
for offer in offers:
    print(f'  Offer ID: {offer.id}')
    print(f'    Selling Price: {offer.selling_price}')
    print(f'    Vendor: {getattr(offer, "vendor", None)}')
    print(f'    Active: {offer.is_active}')
    print(f'    In Stock: {getattr(offer, "is_in_stock", None)}')
    print(f'    Commission Rate: {getattr(offer, "commission_rate", None)}')
    print(f'    ---')

links = AffiliateLink.objects.filter(product=product)
print(f'AffiliateLinks ({links.count()}):')
for link in links:
    print(f'  Link ID: {link.id}')
    print(f'    Platform: {link.platform}')
    print(f'    Platform ID: {link.platform_id}')
    print(f'    Commission Rate: {link.commission_rate}')
    print(f'    Affiliate URL: {link.affiliate_url}')
    print(f'    Original URL: {link.original_url}')
    print(f'    Active: {link.is_active}')
    print(f'    ---') 