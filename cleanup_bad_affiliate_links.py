#!/usr/bin/env python3

import os
import sys
import django

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_platform.settings')

# Mock required environment variables
os.environ.setdefault('GOOGLE_OAUTH2_CLIENT_ID', 'dummy')
os.environ.setdefault('GOOGLE_OAUTH2_CLIENT_SECRET', 'dummy')

django.setup()

if __name__ == "__main__":
    from affiliates.models import AffiliateLink
    
    print("🧹 CLEANING UP INAPPROPRIATE AMAZON AFFILIATE LINKS")
    print("=" * 60)
    
    # Find Amazon affiliate links that point to non-Amazon retailers
    bad_links = AffiliateLink.objects.filter(
        platform='amazon',
        original_url__icontains='cdw.com'
    )
    
    print(f"Found {bad_links.count()} Amazon affiliate links pointing to CDW")
    
    if bad_links.exists():
        print("\nDetails of links to be deleted:")
        for link in bad_links:
            print(f"  ID: {link.id}")
            print(f"  Product: {link.product.name}")
            print(f"  Part Number: {link.product.part_number}")
            print(f"  URL: {link.original_url}")
            print("  ---")
        
        print("\n🗑️  Deleting inappropriate links...")
        deleted_count = bad_links.count()
        bad_links.delete()
        print(f"✅ Deleted {deleted_count} inappropriate Amazon affiliate links")
    else:
        print("✅ No inappropriate links found!")
    
    # Also check for other non-Amazon retailers
    other_bad_links = AffiliateLink.objects.filter(
        platform='amazon'
    ).exclude(
        original_url__icontains='amazon.com'
    ).exclude(
        original_url__icontains='amzn.to'
    ).exclude(
        original_url__icontains=''  # Empty URLs are okay for now
    )
    
    print(f"\nFound {other_bad_links.count()} other potentially bad Amazon affiliate links")
    
    if other_bad_links.exists():
        print("Other potentially inappropriate links (review manually):")
        for link in other_bad_links[:5]:  # Show first 5
            print(f"  ID: {link.id} - {link.original_url}")
    
    print("\n🎯 CLEANUP COMPLETE!") 