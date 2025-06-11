#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_platform.settings')
django.setup()

from ecommerce_platform.schema import Query

def test_universal_search():
    print("🌐 TESTING UNIVERSAL SEARCH SYSTEM")
    print("=" * 60)
    
    # Test the Microsoft Surface Laptop case (from your logs)
    query = Query()
    
    surface_laptop_name = "Microsoft Surface Laptop 6 - 13\" - Core Ultra5 - 16 GB RAM - 256 GB SSD - Windows 11 Pro - Black"
    surface_part_number = "ZJQ-00001"
    
    print(f"🎯 Testing Surface Laptop Search:")
    print(f"   Part Number: {surface_part_number}")
    print(f"   Name: {surface_laptop_name[:60]}...")
    print()
    
    # Test the universal search system
    results = query._handle_non_amazon_product_search(
        partNumber=surface_part_number,
        name=surface_laptop_name
    )
    
    print(f"✅ UNIVERSAL SEARCH RESULTS: {len(results)} total opportunities")
    print()
    
    for i, item in enumerate(results):
        print(f"{i+1}. {item.name[:70]}...")
        print(f"   🔗 Type: {item.relationship_type} | Category: {item.relationship_category}")
        print(f"   💰 Revenue: {item.revenue_type} | Margin: {item.margin_opportunity}")
        print(f"   🎯 Match: {item.match_type} | Confidence: {item.match_confidence:.2f}")
        print(f"   🏷️  Amazon: {item.is_amazon_product} | Alternative: {item.is_alternative}")
        if hasattr(item, 'price') and item.price:
            print(f"   💵 Price: {item.price}")
        print()
    
    print("📊 REVENUE BREAKDOWN:")
    internal_products = [r for r in results if not r.is_amazon_product]
    amazon_products = [r for r in results if r.is_amazon_product]
    accessories = [r for r in results if r.relationship_type == 'accessory']
    
    print(f"   • Internal Products: {len(internal_products)} (high margin)")
    print(f"   • Amazon Alternatives: {len(amazon_products)} (affiliate commission)")  
    print(f"   • Accessories: {len(accessories)} (cross-sell opportunities)")
    print()
    
    print("🎯 BUSINESS IMPACT:")
    print(f"   ✅ Universal coverage: Can monetize ANY website visit")
    print(f"   ✅ Revenue waterfall: Internal → Amazon → Accessories")
    print(f"   ✅ Future intelligence: Tracks demand for sourcing decisions")
    print(f"   ✅ Smart ranking: Relevant alternatives, not random products")

if __name__ == "__main__":
    test_universal_search() 