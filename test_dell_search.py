#!/usr/bin/env python3

import os
import sys
import django
import json

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_platform.settings')

# Mock required environment variables
os.environ.setdefault('GOOGLE_OAUTH2_CLIENT_ID', 'dummy')
os.environ.setdefault('GOOGLE_OAUTH2_CLIENT_SECRET', 'dummy')

django.setup()

# Now test GraphQL
if __name__ == "__main__":
    import graphene
    from ecommerce_platform.schema import schema
    
    print("🔍 TESTING DELL LATITUDE SEARCH")
    print("=" * 50)
    
    # The exact query that's failing from the Chrome extension
    query = """
    query UnifiedProductSearch($asin: String, $partNumber: String, $name: String, $url: String) {
        unifiedProductSearch(
            asin: $asin
            partNumber: $partNumber
            name: $name
            url: $url
        ) {
            id
            name
            title
            partNumber
            isAlternative
            isAmazonProduct
            relationshipType
            relationshipCategory
            matchType
            matchConfidence
            manufacturer {
                name
            }
        }
    }
    """
    
    variables = {
        "partNumber": "VFR3R",
        "name": "Dell Latitude 5550 AI-Ready 15.6\" Laptop – Intel Core Ultra 7 - 16 GB RAM - 512 GB SSD - Windows 11 Pro - 2024 Version"
    }
    
    print(f"🎯 Executing GraphQL query with variables:")
    print(f"   partNumber: {variables['partNumber']}")
    print(f"   name: {variables['name'][:60]}...")
    
    try:
        # Execute the query
        result = schema.execute(query, variable_values=variables)
        
        if result.errors:
            print(f"❌ GraphQL Errors:")
            for error in result.errors:
                print(f"   - {error}")
        else:
            print(f"✅ GraphQL Success!")
            
        print(f"\n📊 Results:")
        if result.data and result.data.get('unifiedProductSearch'):
            products = result.data['unifiedProductSearch']
            print(f"   Found {len(products)} products:")
            for i, product in enumerate(products):
                manufacturer = product.get('manufacturer', {}).get('name', 'Unknown') if product.get('manufacturer') else 'Unknown'
                print(f"   {i+1}. {product.get('name', 'N/A')} ({product.get('partNumber', 'N/A')})")
                print(f"      Manufacturer: {manufacturer}")
                print(f"      Match Type: {product.get('matchType', 'N/A')}")
                print(f"      Relationship: {product.get('relationshipCategory', 'N/A')}")
                print(f"      Alternative: {product.get('isAlternative', False)}")
                print(f"      Confidence: {product.get('matchConfidence', 'N/A')}")
                print()
        else:
            print(f"   ❌ No products found or empty response")
            print(f"   Raw data: {result.data}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎯 TEST COMPLETE") 