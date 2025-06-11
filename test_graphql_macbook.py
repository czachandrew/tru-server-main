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
    
    print("🔍 TESTING GRAPHQL MACBOOK PRO SEARCH")
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
            price
            partNumber
            description
            mainImage
            asin
            isAlternative
            isAmazonProduct
            relationshipType
            relationshipCategory
            marginOpportunity
            revenueType
            matchType
            matchConfidence
            manufacturer {
                name
            }
            affiliateLinks {
                id
                platform
                affiliateUrl
                originalUrl
            }
            offers {
                id
                sellingPrice
                productName
                productPartNumber
                productImage
                vendor {
                    name
                }
            }
        }
    }
    """
    
    variables = {
        "asin": "",
        "partNumber": "MX2Y3LL/A",
        "name": "Apple MacBook Pro - 16\" - M4 Pro - 14‑core CPU - 20‑core GPU - 48 GB RAM - 512 GB SSD - Space Black"
    }
    
    print(f"🎯 Executing GraphQL query with variables:")
    print(f"   partNumber: {variables['partNumber']}")
    print(f"   name: {variables['name'][:50]}...")
    
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
                print(f"   {i+1}. {product.get('name', 'N/A')} ({product.get('partNumber', 'N/A')})")
                print(f"      Match Type: {product.get('matchType', 'N/A')}")
                print(f"      Relationship: {product.get('relationshipType', 'N/A')}")
                print(f"      Amazon Product: {product.get('isAmazonProduct', False)}")
        else:
            print(f"   ❌ No products found or empty response")
            print(f"   Raw data: {result.data}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎯 TEST COMPLETE") 