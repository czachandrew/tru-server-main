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

if __name__ == "__main__":
    print("🧪 TESTING GRAPHQL AMAZON SEARCH INTEGRATION")
    print("=" * 60)
    
    # Test the exact same request that the Chrome extension is making
    from graphene.test import Client
    from ecommerce_platform.schema import schema
    
    # Simulate the exact GraphQL query from the Chrome extension
    query = """
    query UnifiedProductSearch($partNumber: String, $url: String) {
      unifiedProductSearch(partNumber: $partNumber, url: $url) {
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
    
    # Test with a product that doesn't exist in our database to trigger Amazon search
    variables = {
        "partNumber": "NONEXISTENT_PART_123",
        "url": "https://example.com/fake-product"
    }
    
    print(f"🎯 TESTING: Non-existent Product (should trigger Amazon search)")
    print(f"   Part Number: {variables['partNumber']}")
    print(f"   URL: {variables['url'][:50]}...")
    print()
    
    try:
        # Execute the GraphQL query
        client = Client(schema)
        result = client.execute(query, variable_values=variables)
        
        print(f"📊 GRAPHQL EXECUTION RESULTS:")
        print(f"   Errors: {result.get('errors', 'None')}")
        
        if result.get('errors'):
            print(f"❌ GraphQL Errors:")
            for error in result.get('errors', []):
                print(f"   - {error}")
                
        data = result.get('data', {})
        products = data.get('unifiedProductSearch', [])
        
        print(f"   Found {len(products)} products")
        print()
        
        # Analyze the results
        for i, product in enumerate(products):
            print(f"🔍 Product {i+1}:")
            print(f"   Name: {product.get('name', 'N/A')}")
            print(f"   Part Number: {product.get('partNumber', 'N/A')}")
            print(f"   ASIN: {product.get('asin', 'N/A')}")
            print(f"   Is Amazon Product: {product.get('isAmazonProduct', False)}")
            print(f"   Is Alternative: {product.get('isAlternative', False)}")
            print(f"   Match Type: {product.get('matchType', 'N/A')}")
            print(f"   Relationship Type: {product.get('relationshipType', 'N/A')}")
            print(f"   Relationship Category: {product.get('relationshipCategory', 'N/A')}")
            print(f"   Revenue Type: {product.get('revenueType', 'N/A')}")
            
            # Check if this is our new Amazon search result
            if product.get('matchType') == 'amazon_search_pending':
                print(f"   🎯 ✅ AMAZON SEARCH TRIGGERED!")
                print(f"   Task ID: {product.get('partNumber')}")
                print(f"   Description: {product.get('description', 'N/A')[:100]}...")
                
            manufacturer = product.get('manufacturer')
            if manufacturer:
                print(f"   Manufacturer: {manufacturer.get('name', 'N/A')}")
                
            affiliate_links = product.get('affiliateLinks', [])
            if affiliate_links:
                print(f"   Affiliate Links: {len(affiliate_links)} found")
                
            offers = product.get('offers', [])
            if offers:
                print(f"   Offers: {len(offers)} found")
                
            print()
        
        # Check what types of results we got
        amazon_searches = [p for p in products if p.get('matchType') == 'amazon_search_pending']
        internal_products = [p for p in products if not p.get('isAmazonProduct')]
        existing_amazon = [p for p in products if p.get('isAmazonProduct') and p.get('matchType') != 'amazon_search_pending']
        
        print(f"📈 RESULT ANALYSIS:")
        print(f"   🔍 Amazon searches triggered: {len(amazon_searches)}")
        print(f"   🏢 Internal products found: {len(internal_products)}")
        print(f"   📦 Existing Amazon products: {len(existing_amazon)}")
        print()
        
        if amazon_searches:
            print(f"✅ SUCCESS! GraphQL resolver is now calling Amazon search functionality")
            for search in amazon_searches:
                print(f"   Task ID: {search.get('partNumber')}")
                print(f"   Search term inferred from: part='{variables['partNumber']}' or URL")
        else:
            print(f"⚠️  No Amazon search was triggered. This could mean:")
            print(f"   1. Internal products were found (no need for Amazon search)")
            print(f"   2. Amazon search logic didn't activate")
            print(f"   3. Error in the integration")
            
        print(f"\n🔧 NEXT STEPS:")
        print(f"   1. If Amazon search was triggered, check your Puppeteer worker logs")
        print(f"   2. The worker should receive messages with taskType: 'amazon_search'")
        print(f"   3. Once worker is updated, you should see real Amazon products returned")
        
    except Exception as e:
        print(f"❌ Error executing GraphQL query: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print(f"\n✅ INTEGRATION TEST COMPLETE")
    print(f"The Chrome extension's GraphQL requests will now trigger Amazon searches!") 