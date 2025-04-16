import requests
import os
from affiliates.models import AffiliateLink

def generate_amazon_affiliate_url(affiliate_link_id, asin):
    """Generate an Amazon affiliate URL and update the database record"""
    try:
        affiliate_link = AffiliateLink.objects.get(pk=affiliate_link_id)
        
        # Use your Amazon Associates API credentials
        amazon_tag = os.environ.get('AMAZON_ASSOCIATE_TAG', 'defaulttag-20')
        
        # Generate the affiliate URL
        base_url = f"https://www.amazon.com/dp/{asin}"
        affiliate_url = f"{base_url}?tag={amazon_tag}"
        
        # Update the record
        affiliate_link.affiliate_url = affiliate_url
        affiliate_link.save()
        
        return True
    except Exception as e:
        print(f"Error generating Amazon affiliate URL: {str(e)}")
        return False