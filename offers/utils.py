"""
Hybrid Offer System Utilities

Utilities for managing the unified offer system that supports both 
supplier offers and affiliate referral offers.
"""

import re
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from .models import Offer
from vendors.models import Vendor
from affiliates.models import AffiliateLink


def parse_price_string(price_str):
    """
    Parse a price string and return a clean Decimal value
    
    Handles formats like:
    - "$99.99"
    - "$99..99" (malformed)
    - "99.99"
    - "99,99" (European format)
    - "$1,299.99"
    
    Args:
        price_str: Price string to parse
        
    Returns:
        Decimal: Cleaned price value
        
    Raises:
        ValueError: If price cannot be parsed
    """
    if not price_str or str(price_str).strip() == '':
        return Decimal('0.00')
    
    # Convert to string if not already
    price_str = str(price_str).strip()
    
    # Remove currency symbols (but keep digits, commas, and dots)
    # This regex removes everything except digits, commas, and periods
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    
    if not cleaned:
        return Decimal('0.00')
    
    # Handle malformed prices like "99..99" -> "99.99"
    # Replace multiple consecutive dots with a single dot
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    
    # Remove leading dots
    cleaned = re.sub(r'^\.+', '', cleaned)
    
    # If empty after cleaning, return 0
    if not cleaned:
        return Decimal('0.00')
    
    # Handle comma thousands separators "1,299.99"
    if ',' in cleaned and '.' in cleaned:
        # If both comma and dot, assume comma is thousands separator
        # Split by dot to separate the decimal part
        parts = cleaned.split('.')
        if len(parts) == 2 and len(parts[1]) <= 2:  # Cents part should be 1-2 digits
            main_part = parts[0].replace(',', '')  # Remove commas from the main part
            cents_part = parts[1]
            cleaned = f"{main_part}.{cents_part}"
        else:
            # Multiple dots, just remove commas and keep the last part as decimal
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        # Only comma - could be European format (99,99) or thousands (1,299)
        comma_parts = cleaned.split(',')
        if len(comma_parts) == 2 and len(comma_parts[1]) <= 2:
            # European format - replace comma with dot
            cleaned = cleaned.replace(',', '.')
        else:
            # Thousands separator - remove commas
            cleaned = cleaned.replace(',', '')
    
    # Ensure there's only one decimal point
    if cleaned.count('.') > 1:
        # Keep only the last decimal point
        parts = cleaned.split('.')
        main_part = ''.join(parts[:-1])
        decimal_part = parts[-1]
        cleaned = f"{main_part}.{decimal_part}"
    
    # Add leading zero if starts with decimal
    if cleaned.startswith('.'):
        cleaned = '0' + cleaned
    
    try:
        result = Decimal(cleaned)
        # Ensure 2 decimal places for proper formatting
        return result.quantize(Decimal('0.00'))
    except (InvalidOperation, ValueError) as e:
        return Decimal('0.00')


def create_affiliate_offer_from_link(affiliate_link, current_price, commission_rate=None):
    """
    Create or update an affiliate offer from an AffiliateLink
    
    Args:
        affiliate_link: AffiliateLink instance
        current_price: Current price from affiliate platform (string or Decimal)
        commission_rate: Commission rate (uses link's rate if not provided)
    
    Returns:
        tuple: (Offer instance, created_boolean)
    """
    # Parse and clean the price
    if isinstance(current_price, str):
        try:
            current_price = parse_price_string(current_price)
        except ValueError as e:
            raise ValueError(f"Invalid price format: {e}")
    elif not isinstance(current_price, Decimal):
        current_price = Decimal(str(current_price))
    
    # Get or create affiliate vendor
    vendor, _ = Vendor.objects.get_or_create(
        name=f"{affiliate_link.platform.title()} Marketplace",
        defaults={
            'slug': f"{affiliate_link.platform}-marketplace",
            'code': f"{affiliate_link.platform.upper()}_MKT",
            'vendor_type': 'affiliate',
            'is_affiliate': True,
            'website': f"https://{affiliate_link.platform}.com",
            'description': f"Affiliate marketplace for {affiliate_link.platform}",
            'affiliate_program': f"{affiliate_link.platform.title()} Associates",
            'default_commission_rate': commission_rate or affiliate_link.commission_rate
        }
    )
    
    # Create or update the offer
    offer, created = Offer.objects.update_or_create(
        product=affiliate_link.product,
        vendor=vendor,
        offer_type='affiliate',
        defaults={
            'selling_price': current_price,
            'vendor_sku': affiliate_link.platform_id,
            'vendor_url': affiliate_link.original_url[:500] if affiliate_link.original_url else '',  # Truncate to fit field limit
            'commission_rate': commission_rate or affiliate_link.commission_rate,
            'is_in_stock': True,
            'stock_quantity': 999,  # Placeholder for affiliate offers
            'price_last_updated': timezone.now(),
        }
    )
    
    # Connect the affiliate link to the offer
    affiliate_link.offer = offer
    affiliate_link.save(update_fields=['offer'])
    
    return offer, created


def get_best_offers_for_product(product_id, limit=5, include_affiliate=True, include_supplier=True):
    """
    Get the best offers for a product across all sources
    
    Args:
        product_id: Product ID
        limit: Maximum number of offers to return
        include_affiliate: Include affiliate offers
        include_supplier: Include supplier offers
    
    Returns:
        QuerySet: Best offers ordered by price
    """
    queryset = Offer.objects.filter(
        product_id=product_id,
        is_active=True,
        is_in_stock=True
    )
    
    # Filter by offer types
    offer_types = []
    if include_supplier:
        offer_types.append('supplier')
    if include_affiliate:
        offer_types.append('affiliate')
    
    if offer_types:
        queryset = queryset.filter(offer_type__in=offer_types)
    
    return queryset.select_related('product', 'vendor').order_by('selling_price')[:limit]


def get_price_intelligence_summary(product_id):
    """
    Get comprehensive price intelligence for a product
    
    Args:
        product_id: Product ID
    
    Returns:
        dict: Price intelligence data
    """
    offers = Offer.objects.filter(
        product_id=product_id,
        is_active=True,
        is_in_stock=True
    ).select_related('vendor')
    
    if not offers.exists():
        return None
    
    supplier_offers = offers.filter(offer_type='supplier')
    affiliate_offers = offers.filter(offer_type='affiliate')
    
    # Calculate price statistics
    all_prices = [offer.selling_price for offer in offers]
    supplier_prices = [offer.selling_price for offer in supplier_offers]
    affiliate_prices = [offer.selling_price for offer in affiliate_offers]
    
    return {
        'total_offers': offers.count(),
        'supplier_offers': supplier_offers.count(),
        'affiliate_offers': affiliate_offers.count(),
        'lowest_price': min(all_prices),
        'highest_price': max(all_prices),
        'average_price': sum(all_prices) / len(all_prices),
        'lowest_supplier_price': min(supplier_prices) if supplier_prices else None,
        'lowest_affiliate_price': min(affiliate_prices) if affiliate_prices else None,
        'price_range': max(all_prices) - min(all_prices),
        'best_offer': offers.order_by('selling_price').first(),
        'commission_potential': sum([
            (offer.selling_price * offer.commission_rate) / 100 
            for offer in affiliate_offers 
            if offer.commission_rate
        ])
    } 