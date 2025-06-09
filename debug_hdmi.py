#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_platform.settings')
django.setup()

from products.consumer_matching import smart_extract_search_terms_dynamic, get_consumer_focused_results
from products.models import Product

def test_hdmi_matching():
    print("🔍 HDMI Cable Matching Debug")
    print("=" * 50)
    
    # Test the Amazon HDMI cable extraction
    amazon_name = "ANKER HDMI Cable 8K@60Hz, 6FT Ultra HD 4K@120Hz HDMI 2.1 Cord,48 Gbps Certified Ultra High-Speed,Compatible with PlayStation 5,Xbox,Samsung TVs,and More"
    
    print("1. AMAZON HDMI EXTRACTION:")
    result = smart_extract_search_terms_dynamic(amazon_name)
    print(f"   Type: {result.get('type')}")
    print(f"   Method: {result.get('method')}")
    print(f"   Clean terms: {result.get('clean_terms')}")
    print(f"   Confidence: {result.get('confidence')}")
    print()
    
    # Check if we can find the StarTech HDMI cable
    print("2. STARTECH HDMI SEARCH:")
    startech_products = Product.objects.filter(part_number__icontains='HDMI')
    print(f"   Found {startech_products.count()} products with 'HDMI' in part number:")
    for p in startech_products[:3]:
        print(f"   - {p.name} (Part: {p.part_number})")
    print()
    
    # Search for any HDMI cables by name
    print("3. HDMI PRODUCTS BY NAME:")
    hdmi_products = Product.objects.filter(name__icontains='hdmi')[:5]
    print(f"   Found {hdmi_products.count()} products with 'hdmi' in name:")
    for p in hdmi_products:
        print(f"   - {p.name} (Part: {p.part_number})")
    print()
    
    # Test the consumer matching
    print("4. CONSUMER MATCHING TEST:")
    consumer_results = get_consumer_focused_results("hdmi cable", None)
    print(f"   Found {len(consumer_results['results'])} results:")
    for i, item in enumerate(consumer_results['results'][:3]):
        product = item['product']
        print(f"   {i+1}. {product.name if hasattr(product, 'name') else 'N/A'}")
        print(f"      Alternative: {item.get('isAlternative', False)}")
        print(f"      Relationship: {item.get('relationshipType', 'N/A')}")
    print()
    
    # Test specific search terms that should work
    print("5. SIMPLE HDMI SEARCH:")
    simple_hdmi = Product.objects.filter(
        Q(name__icontains='hdmi') | Q(part_number__icontains='hdmi')
    ).exclude(name__icontains='vga')[:5]
    print(f"   Found {simple_hdmi.count()} HDMI products (excluding VGA):")
    for p in simple_hdmi:
        print(f"   - {p.name} (Part: {p.part_number})")

if __name__ == "__main__":
    from django.db.models import Q
    test_hdmi_matching() 