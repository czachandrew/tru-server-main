#!/usr/bin/env python3

import os
import sys
import django
from collections import Counter, defaultdict
import re

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_platform.settings')
django.setup()

from products.models import Product, Manufacturer
from django.db.models import Q

def analyze_inventory():
    """Comprehensive analysis of current inventory for consumer product strategy"""
    
    print("🔍 COMPREHENSIVE INVENTORY ANALYSIS")
    print("=" * 60)
    
    # Basic stats
    total_products = Product.objects.count()
    partner_products = Product.objects.filter(source='partner_import').count()
    amazon_products = Product.objects.filter(source='amazon').count()
    
    print(f"\n📊 BASIC STATISTICS:")
    print(f"Total products: {total_products:,}")
    print(f"Partner imports (Synnex): {partner_products:,} ({partner_products/total_products*100:.1f}%)")
    print(f"Amazon products: {amazon_products:,} ({amazon_products/total_products*100:.1f}%)")
    
    # Manufacturer analysis
    print(f"\n🏭 MANUFACTURER BREAKDOWN:")
    manufacturers = Product.objects.filter(source='partner_import').values_list('manufacturer__name', flat=True)
    mfr_counts = Counter(manufacturers)
    
    # Categorize manufacturers
    enterprise_brands = ['PANDUIT CORP', 'EATON', 'APC BY SCHNEIDER ELECTRIC', 'LEGRAND DAT', 'CHIEF MANUFACTURING']
    consumer_tech_brands = ['HP INC.', 'INTEL', 'XEROX', 'LEXMARK', 'SHARP ELECTRONICS CORPORATION']
    accessory_brands = ['STARTECH.COM', 'C2G', 'AXIOM', 'COMPULOCKS BRANDS, INC.']
    
    enterprise_count = sum(mfr_counts.get(brand, 0) for brand in enterprise_brands)
    consumer_tech_count = sum(mfr_counts.get(brand, 0) for brand in consumer_tech_brands)
    accessory_count = sum(mfr_counts.get(brand, 0) for brand in accessory_brands)
    
    print(f"Enterprise/Infrastructure: {enterprise_count:,} ({enterprise_count/partner_products*100:.1f}%)")
    print(f"Consumer Tech (HP, Intel, etc.): {consumer_tech_count:,} ({consumer_tech_count/partner_products*100:.1f}%)")
    print(f"Accessories/Cables: {accessory_count:,} ({accessory_count/partner_products*100:.1f}%)")
    
    # Consumer product potential analysis
    print(f"\n🛒 CONSUMER PRODUCT POTENTIAL:")
    
    # Search for actual consumer devices vs accessories
    consumer_device_queries = [
        ("Laptops/Notebooks", ["laptop", "notebook", "thinkpad", "pavilion", "inspiron"]),
        ("Desktops/PCs", ["desktop", "pc ", "workstation", "optiplex", "prodesk"]),
        ("Monitors/Displays", ["monitor", "display", "lcd", "led", "oled", "4k", "gaming monitor"]),
        ("Printers", ["printer", "inkjet", "laserjet", "multifunction", "mfp"]),
        ("Keyboards/Mice", ["keyboard", "mouse", "wireless keyboard", "gaming keyboard", "mechanical"]),
        ("Headsets/Audio", ["headset", "headphones", "speaker", "audio", "microphone"]),
        ("Networking", ["router", "wifi", "wireless", "access point", "modem"]),
        ("Storage", ["ssd", "hard drive", "external drive", "usb drive", "flash drive"]),
        ("Graphics Cards", ["graphics card", "video card", "nvidia", "radeon", "gpu"]),
        ("Tablets/Mobile", ["tablet", "ipad", "surface", "mobile", "smartphone"])
    ]
    
    for category, keywords in consumer_device_queries:
        query = Q()
        for keyword in keywords:
            query |= Q(description__icontains=keyword)
        
        count = Product.objects.filter(query, source='partner_import').count()
        if count > 0:
            print(f"{category}: {count:,} products")
            
            # Get a few examples
            examples = Product.objects.filter(query, source='partner_import')[:3]
            for ex in examples:
                clean_desc = ex.description.replace('\n', ' ').replace('\r', '')[:100]
                print(f"  - {ex.name[:30]}... | {clean_desc}...")
            print()
    
    # Description pattern analysis
    print(f"\n📝 DESCRIPTION PATTERN ANALYSIS:")
    sample_descriptions = Product.objects.filter(source='partner_import')[:1000].values_list('description', flat=True)
    
    # Common patterns
    patterns = {
        'Part numbers in parens': r'\([A-Z0-9\-]+\)',
        'Model numbers': r'MODEL:?\s*[A-Z0-9\-]+',
        'Renewed/Refurb': r'(renewed|refurbished|open box|used)',
        'Specs (RAM/Storage)': r'(\d+GB|\d+TB|\d+MHz|\d+GHz)',
        'Brand mentions': r'(HP|DELL|LENOVO|INTEL|AMD|NVIDIA|MICROSOFT|APPLE|ASUS|ACER)',
        'Consumer terms': r'(gaming|home|personal|consumer|desktop|laptop)'
    }
    
    for pattern_name, regex in patterns.items():
        matches = sum(1 for desc in sample_descriptions if re.search(regex, desc, re.IGNORECASE))
        print(f"{pattern_name}: {matches}/1000 ({matches/10:.1f}%)")
    
    print(f"\n💡 STRATEGIC RECOMMENDATIONS:")
    print("=" * 60)
    
    if consumer_tech_count < partner_products * 0.2:  # Less than 20% consumer tech
        print("⚠️  INSIGHT: Your inventory is heavily enterprise/B2B focused")
        print("   Recommendation: Prioritize Amazon affiliate links for consumer products")
        print("   Strategy: Use your inventory for accessories/parts, Amazon for main devices")
    
    print("\n🔄 MATCHING STRATEGY RECOMMENDATIONS:")
    print("1. Description Mining: Extract model numbers, specs from descriptions")
    print("2. Dual Approach: Search your inventory first, then Amazon as primary option")
    print("3. Cross-selling: When showing Amazon consumer device, show your accessories")
    print("4. Category Mapping: Map consumer searches to enterprise equivalents")
    
    return {
        'total_products': total_products,
        'partner_products': partner_products,
        'amazon_products': amazon_products,
        'enterprise_ratio': enterprise_count / partner_products,
        'consumer_tech_ratio': consumer_tech_count / partner_products,
        'accessory_ratio': accessory_count / partner_products
    }

if __name__ == "__main__":
    results = analyze_inventory() 