import graphene
import logging
import json
import re
import os
import datetime
import traceback
import uuid
from urllib.parse import urlparse
from typing import List, Optional
from dataclasses import dataclass
from functools import lru_cache
from collections import Counter
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.utils import timezone
import redis
from django_q.tasks import async_task
from django.conf import settings
from django.utils.text import slugify

from products.models import Product, Category, Manufacturer
from offers.models import Offer
from affiliates.models import AffiliateLink, ProductAssociation
from affiliates.tasks import generate_standalone_amazon_affiliate_url, generate_affiliate_url_from_search

from ..types.product import ProductType, CategoryType, ManufacturerType
from ..types.offer import OfferType, OfferTypeEnum

# Add NLTK import for stopwords (with fallback)
try:
    from nltk.corpus import stopwords
except ImportError:
    # Fallback if NLTK is not available
    class stopwords:
        @staticmethod
        def words(lang):
            return ['the', 'and', 'with', 'for', 'this', 'that', 'from', 'to', 'in', 'of', 'a', 'an']

User = get_user_model()

# Create a custom debug logger that writes to a specific file
debug_logger = logging.getLogger('debug_search')
debug_logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
os.makedirs(logs_dir, exist_ok=True)

# Create a file handler with today's date in the filename
today = datetime.datetime.now().strftime('%Y-%m-%d')
log_file = os.path.join(logs_dir, f'search_debug_{today}.log')

file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
file_handler.setFormatter(formatter)
debug_logger.addHandler(file_handler)

class ProductExistsResponse(graphene.ObjectType):
    exists = graphene.Boolean()
    product = graphene.Field(ProductType)
    affiliate_link = graphene.Field('ecommerce_platform.graphql.types.affiliate.AffiliateLinkType')
    needs_affiliate_generation = graphene.Boolean()
    message = graphene.String()

class ProductSearchResult(graphene.ObjectType):
    """Enhanced wrapper type for product search results with detailed relationship classification"""
    id = graphene.ID()
    name = graphene.String()
    part_number = graphene.String()
    description = graphene.String()
    main_image = graphene.String()
    manufacturer = graphene.Field(ManufacturerType)
    affiliate_links = graphene.List('ecommerce_platform.graphql.types.affiliate.AffiliateLinkType')
    offers = graphene.List(OfferType)
    
    # ENHANCED: Product relationship classification
    is_amazon_product = graphene.Boolean()
    is_alternative = graphene.Boolean()  # Keep for backward compatibility
    
    # NEW: Detailed relationship type
    relationship_type = graphene.String()  # 'primary', 'equivalent', 'accessory', 'cross_sell', 'enterprise_alternative'
    relationship_category = graphene.String()  # 'exact_match', 'supplier_alternative', 'laptop_accessory', 'monitor_cable', etc.
    
    # NEW: Business value indicators
    margin_opportunity = graphene.String()  # 'high', 'medium', 'low', 'affiliate_only'
    revenue_type = graphene.String()  # 'product_sale', 'affiliate_commission', 'cross_sell_opportunity'
    
    # Enhanced matching information
    match_type = graphene.String()  # Keep existing for compatibility
    match_confidence = graphene.Float()
    
    # Consumer-focused fields (Amazon API compatibility)
    title = graphene.String()  # Amazon product title
    price = graphene.String()  # Price as string (can include currency)
    currency = graphene.String()  # Currency code
    availability = graphene.String()  # Availability status
    product_url = graphene.String()  # Direct product URL
    image_url = graphene.String()  # Main product image URL
    asin = graphene.String()  # Amazon ASIN
    
    # BACKWARD COMPATIBILITY: Chrome extension expects a 'product' field
    product = graphene.Field(ProductType)
    
    # Add camelCase aliases for frontend compatibility
    partNumber = graphene.String()
    mainImage = graphene.String()
    affiliateLinks = graphene.List('ecommerce_platform.graphql.types.affiliate.AffiliateLinkType')
    isAmazonProduct = graphene.Boolean()
    isAlternative = graphene.Boolean()
    relationshipType = graphene.String()
    relationshipCategory = graphene.String()
    marginOpportunity = graphene.String()
    revenueType = graphene.String()
    matchType = graphene.String()
    matchConfidence = graphene.Float()
    productUrl = graphene.String()
    imageUrl = graphene.String()

    def resolve_partNumber(self, info):
        return self.part_number

    def resolve_mainImage(self, info):
        return self.main_image or self.image_url

    def resolve_affiliateLinks(self, info):
        """
        CRITICAL: Always return affiliate links for Amazon products
        This ensures Chrome extension gets affiliate URLs
        """
        if self.affiliate_links:
            return self.affiliate_links
        
        # For Amazon products, ensure we get the affiliate link
        if self.is_amazon_product and self.asin:
            try:
                affiliate_links = AffiliateLink.objects.filter(
                    platform='amazon',
                    platform_id=self.asin
                )
                
                if affiliate_links.exists():
                    debug_logger.info(f"🔗 Found {affiliate_links.count()} affiliate links for ASIN {self.asin}")
                    return list(affiliate_links)
                else:
                    debug_logger.warning(f"⚠️ No affiliate links found for ASIN {self.asin}")
                    
            except Exception as e:
                debug_logger.error(f"❌ Error getting affiliate links: {e}")
        
        # For supplier products, get links from the source product
        if hasattr(self, '_source_product') and self._source_product:
            return list(AffiliateLink.objects.filter(product=self._source_product))
        
        return []
    
    def resolve_offers(self, info):
        """
        CRITICAL: Return offers from the unified offer system
        This is essential for Chrome extension to see affiliate opportunities
        """
        if hasattr(self, 'offers') and self.offers:
            return self.offers
        
        # For products with a source product, get offers from the database
        if hasattr(self, '_source_product') and self._source_product:
            try:
                from offers.models import Offer
                offers = Offer.objects.filter(product=self._source_product, is_active=True).select_related('vendor')
                debug_logger.info(f"🎯 Found {offers.count()} offers for product {self._source_product.name}")
                return list(offers)
            except Exception as e:
                debug_logger.error(f"❌ Error getting offers for source product: {e}")
        
        # For Amazon products, check if we have affiliate links that correspond to offers
        if self.is_amazon_product and self.asin:
            try:
                from offers.models import Offer
                # Find affiliate link for this ASIN
                affiliate_link = AffiliateLink.objects.filter(
                    platform='amazon',
                    platform_id=self.asin
                ).first()
                
                if affiliate_link and affiliate_link.product:
                    # Get offers for the product associated with this affiliate link
                    offers = Offer.objects.filter(
                        product=affiliate_link.product,
                        is_active=True
                    ).select_related('vendor')
                    debug_logger.info(f"🎯 Found {offers.count()} offers via affiliate link for ASIN {self.asin}")
                    return list(offers)
                else:
                    debug_logger.warning(f"⚠️ No affiliate link or associated product for ASIN {self.asin}")
                    
            except Exception as e:
                debug_logger.error(f"❌ Error getting offers for ASIN: {e}")
        
        # If we have a product ID, try to get offers directly
        if self.id and self.id != 'amazon_' + str(self.asin):
            try:
                from offers.models import Offer
                offers = Offer.objects.filter(product_id=self.id, is_active=True).select_related('vendor')
                debug_logger.info(f"🎯 Found {offers.count()} offers for product ID {self.id}")
                return list(offers)
            except Exception as e:
                debug_logger.error(f"❌ Error getting offers for product ID: {e}")
        
        debug_logger.warning(f"⚠️ No offers found for ProductSearchResult: ID={self.id}, ASIN={getattr(self, 'asin', None)}")
        return []

    def resolve_isAmazonProduct(self, info):
        return self.is_amazon_product

    def resolve_isAlternative(self, info):
        return self.is_alternative
    
    def resolve_relationshipType(self, info):
        return self.relationship_type
    
    def resolve_relationshipCategory(self, info):
        return self.relationship_category
    
    def resolve_marginOpportunity(self, info):
        return self.margin_opportunity
    
    def resolve_revenueType(self, info):
        return self.revenue_type

    def resolve_matchType(self, info):
        return self.match_type

    def resolve_matchConfidence(self, info):
        return self.match_confidence
    
    def resolve_productUrl(self, info):
        return self.product_url
    
    def resolve_imageUrl(self, info):
        return self.image_url
    
    # Provide fallbacks for title/name
    def resolve_title(self, info):
        return self.title or self.name
    
    def resolve_name(self, info):
        return self.name or self.title
    
    def resolve_product(self, info):
        """
        BACKWARD COMPATIBILITY: Return a ProductType object for Chrome extension
        Create a dynamic ProductType from the search result data
        """
        if hasattr(self, '_source_product') and self._source_product:
            return self._source_product
        
        # For Amazon products or when no source product, handle gracefully
        if self.is_amazon_product and self.asin:
            try:
                amazon_product = get_amazon_product_by_asin(self.asin)
                if amazon_product:
                    return amazon_product
                    
                affiliate_link = AffiliateLink.objects.filter(
                    platform='amazon',
                    platform_id=self.asin
                ).first()
                
                if affiliate_link and affiliate_link.product:
                    return affiliate_link.product
                
            except Exception as e:
                debug_logger.error(f"Error finding Amazon product: {e}")
        
        # Try to find the product by ID
        if self.id:
            try:
                return Product.objects.get(id=self.id)
            except Product.DoesNotExist:
                pass
        
        return None
    
    def resolve_affiliateLinks(self, info):
        """
        CRITICAL: Always return affiliate links for Amazon products
        This ensures Chrome extension gets affiliate URLs
        """
        if self.affiliate_links:
            return self.affiliate_links
        
        # For Amazon products, ensure we get the affiliate link
        if self.is_amazon_product and self.asin:
            try:
                affiliate_links = AffiliateLink.objects.filter(
                    platform='amazon',
                    platform_id=self.asin
                )
                
                if affiliate_links.exists():
                    debug_logger.info(f"🔗 Found {affiliate_links.count()} affiliate links for ASIN {self.asin}")
                    return list(affiliate_links)
                else:
                    debug_logger.warning(f"⚠️ No affiliate links found for ASIN {self.asin}")
                    
            except Exception as e:
                debug_logger.error(f"❌ Error getting affiliate links: {e}")
        
        # For supplier products, get links from the source product
        if hasattr(self, '_source_product') and self._source_product:
            return list(AffiliateLink.objects.filter(product=self._source_product))
        
        return []

class ProductQuery(graphene.ObjectType):
    # Basic product queries
    product = graphene.Field(ProductType, id=graphene.ID(), part_number=graphene.String())
    products = graphene.List(
        ProductType,
        search=graphene.String(),
        category_id=graphene.ID(),
        manufacturer_id=graphene.ID(),
        limit=graphene.Int(),
        offset=graphene.Int()
    )
    
    # Category and manufacturer queries
    categories = graphene.List(CategoryType, parent_id=graphene.ID())
    category = graphene.Field(CategoryType, id=graphene.ID(required=True))
    manufacturers = graphene.List(ManufacturerType)
    manufacturer = graphene.Field(ManufacturerType, id=graphene.ID(required=True))
    
    # Product existence check
    product_exists = graphene.Field(
        ProductExistsResponse,
        part_number=graphene.String(required=True),
        asin=graphene.String(),
        url=graphene.String()
    )
    
    # Featured products
    featured_products = graphene.List(ProductType, limit=graphene.Int())
    featuredProducts = graphene.List(ProductType, limit=graphene.Int())  # camelCase alias
    
    # CORE BUSINESS LOGIC: Unified search functionality
    unified_product_search = graphene.List(
        ProductSearchResult,
        asin=graphene.String(),
        part_number=graphene.String(),
        name=graphene.String(),
        url=graphene.String(),
        description="Unified search endpoint for Chrome extension"
    )
    
    # Add camelCase alias for Chrome extension compatibility
    unifiedProductSearch = graphene.List(
        ProductSearchResult,
        asin=graphene.String(),
        partNumber=graphene.String(),
        name=graphene.String(),
        url=graphene.String(),
        description="Unified search endpoint for Chrome extension (camelCase)"
    )
    
    # Debug queries
    debug_asin_lookup = graphene.Field(
        graphene.String,
        asin=graphene.String(required=True),
        description="Debug endpoint to check ASIN lookup"
    )
    
    def resolve_product(self, info, id=None, part_number=None):
        """Find a single product by ID or part number"""
        product = None
        if id:
            product = Product.objects.get(pk=id)
        elif part_number:
            product = Product.objects.get(part_number=part_number)
        
        if product:
            # Ensure this product has an Amazon affiliate link if needed
            ensure_product_has_amazon_affiliate_link(product)
        
        return product
    
    def resolve_products(self, info, search=None, category_id=None, 
                         manufacturer_id=None, limit=None, offset=None):
        products = Product.objects.all()
        
        if search:
            if hasattr(Product, 'search_vector') and Product.objects.filter(search_vector__isnull=False).exists():
                products = products.filter(search_vector=search)
            else:
                # Fallback to basic search if search_vector is not available
                products = products.filter(
                    Q(name__icontains=search) | 
                    Q(description__icontains=search) |
                    Q(part_number__icontains=search)
                )
        
        if category_id:
            products = products.filter(categories__id=category_id)
        
        if manufacturer_id:
            products = products.filter(manufacturer_id=manufacturer_id)
        
        # Apply pagination
        if offset is not None:
            products = products[offset:]
        if limit is not None:
            products = products[:limit]
            
        return products
    
    def resolve_categories(self, info, parent_id=None):
        if parent_id:
            return Category.objects.filter(parent_id=parent_id)
        return Category.objects.filter(parent__isnull=True)
    
    def resolve_category(self, info, id):
        return Category.objects.get(pk=id)
    
    def resolve_manufacturers(self, info):
        return Manufacturer.objects.all()
    
    def resolve_manufacturer(self, info, id):
        return Manufacturer.objects.get(pk=id)
    
    def resolve_product_exists(self, info, part_number, asin=None, url=None):
        debug_logger.info(f"🔍 Product lookup: part_number='{part_number}', asin='{asin}'")
        
        # CACHE THE ASIN for later use in SearchProducts
        if asin:
            try:
                import redis
                redis_kwargs = get_redis_connection()
                r = redis.Redis(**redis_kwargs)
                # Store ASIN with the search term as key for 10 minutes
                cache_key = f"recent_asin:{part_number.lower().replace(' ', '_')}"
                r.set(cache_key, asin, ex=600)  # 10 minutes
                debug_logger.info(f"💾 Cached ASIN '{asin}' for term '{part_number}'")
            except Exception as e:
                debug_logger.warning(f"⚠️ Failed to cache ASIN: {str(e)}")
        
        product = None
        match_method = "none"
        
        # STRATEGY 1: Exact part number match
        try:
            product = Product.objects.prefetch_related(
                'offers', 'offers__vendor', 'affiliate_links', 'manufacturer', 'categories'
            ).get(part_number__iexact=part_number)
            match_method = "exact_part_number"
            debug_logger.info(f"✅ Found by exact part number: {product.name}")
        except Product.DoesNotExist:
            debug_logger.info(f"❌ No exact part number match for: {part_number}")
        
        # STRATEGY 2: Fuzzy name matching
        if not product:
            debug_logger.info(f"🔍 Trying fuzzy name matching...")
            
            # Extract key terms from the search
            search_terms = extract_search_terms(part_number)
            debug_logger.info(f"📝 Extracted terms: {search_terms}")
            
            # Try different combinations
            candidates = find_product_candidates(search_terms)
            
            if candidates:
                # Score and pick the best match
                product = score_and_select_best_match(part_number, candidates)
                if product:
                    match_method = "fuzzy_name"
                    debug_logger.info(f"✅ Found by fuzzy matching: {product.name} (part: {product.part_number})")
        
        # STRATEGY 3: ASIN-based lookup
        if not product and asin:
            debug_logger.info(f"🔍 Trying ASIN-based lookup...")
            
            # Check if we have an existing affiliate link with this ASIN
            existing_links = AffiliateLink.objects.filter(
                        platform='amazon',
                        platform_id=asin
            ).select_related('product')
            
            if existing_links.exists():
                product = existing_links.first().product
                match_method = "asin_link"
                debug_logger.info(f"✅ Found by existing ASIN link: {product.name}")
        
        # If we found a product, handle the response
        if product:
            debug_logger.info(f"🎯 Final match: {product.name} (method: {match_method})")
            
            # Log offers and affiliate links for debugging
            offers = list(product.offers.all())
            affiliate_links = list(product.affiliate_links.all())
            debug_logger.info(f"📊 Product has {len(offers)} offers, {len(affiliate_links)} affiliate links")
            
            # Handle ASIN affiliate link creation/lookup
            if asin:
                affiliate_link = handle_affiliate_link_for_asin(product, asin, url)
                if affiliate_link:
                    return ProductExistsResponse(
                        exists=True,
                        product=product,
                        affiliate_link=affiliate_link,
                    needs_affiliate_generation=(affiliate_link.affiliate_url == ''),
                    message=f"Product found via {match_method}. Affiliate link {'found' if affiliate_link.affiliate_url else 'queued'}.")
            
            return ProductExistsResponse(
                exists=True,
                product=product,
                affiliate_link=None,
                needs_affiliate_generation=False,
                message=f"Product found via {match_method}"
            )
                
        # No product found
        debug_logger.warning(f"❌ No product found for: {part_number}")
        if asin:
            affiliate_link = handle_affiliate_link_for_asin(product, asin, url)
            if affiliate_link:
                return ProductExistsResponse(
                    exists=True,
                    product=product,
                    affiliate_link=affiliate_link,
                    needs_affiliate_generation=(affiliate_link.affiliate_url == ''),
                    message=f"Product found via {match_method}. Affiliate link {'found' if affiliate_link.affiliate_url else 'queued'}.")
        
        return ProductExistsResponse(
                exists=False,
                product=None,
                affiliate_link=None,
                needs_affiliate_generation=False,
                message="Product not found in database"
            )
    
    def resolve_featured_products(self, info, limit=None):
        """Resolver to get featured products based on featured flag"""
        # First try to get products marked as featured
        queryset = Product.objects.filter(status='active', is_featured=True)
        
        # If no featured products, fall back to newest products
        if queryset.count() == 0:
            queryset = Product.objects.filter(status='active').order_by('-created_at')
        
        # Prefetch related data to avoid N+1 query issues
        queryset = queryset.prefetch_related(
            'manufacturer',
            'categories',
            'offers',
            'offers__vendor'
        )
        
        # Apply limit if provided
        if limit:
            queryset = queryset[:limit]
        
        return queryset
    
    def resolve_featuredProducts(self, info, limit=None):
        """camelCase alias for featured products"""
        return self.resolve_featured_products(info, limit)
    
    def resolve_unifiedProductSearch(self, info, asin=None, partNumber=None, name=None, url=None):
        """
        UNIFIED MULTI-RETAILER SEARCH (CHROME EXTENSION)
        
        ENHANCED UNIVERSAL REVENUE STRATEGY:
        1. Try internal inventory first (highest margin)
        2. Dynamic Amazon search with affiliate links (reliable commission)  
        3. Find relevant accessories (cross-sell opportunities)
        4. Create product records for future monetization
        
        Self-contained resolver for Chrome extension searches across:
        - Amazon (ASIN)
        - Best Buy (SKU)  
        - Staples (Item Number)
        - CDW (Part Number)
        - Newegg (Item Number)
        - Microsoft Store (Part Number)
        - Any retail site (product name/URL)
        
        Priority: ASIN -> partNumber -> name -> URL parsing
        """
        try:
            debug_logger.info(f"🔍 Chrome Extension Universal Search - ASIN: {asin}, Part: {partNumber}, Name: {name}, URL: {url}")
            
            # PRIORITY 1: ASIN Search (Amazon) - FIXED: Only direct affiliate link creation
            if asin:
                debug_logger.info(f"🎯 Amazon ASIN Search: {asin} (DIRECT AFFILIATE LINK ONLY)")
                
                # CORE BUSINESS LOGIC: Always ensure affiliate link exists for ASIN
                affiliate_link = ensure_affiliate_link_exists(asin)
                debug_logger.info(f"🔗 Affiliate link: {'✅ Found' if affiliate_link and affiliate_link.affiliate_url else '⏳ Pending/Created'}")
                
                # Try to find existing Amazon product for this ASIN
                amazon_product = get_amazon_product_by_asin(asin)
                
                results = []
                
                if amazon_product:
                    # We have an Amazon product in our database
                    result = ProductSearchResult(
                        id=amazon_product.id,
                        title=amazon_product.name,
                        name=amazon_product.name,
                        part_number=amazon_product.part_number,
                        description=amazon_product.description,
                        main_image=amazon_product.main_image,
                        manufacturer=amazon_product.manufacturer,
                        asin=asin,
                        is_amazon_product=True,
                        is_alternative=False,
                        match_type="exact_asin",
                        match_confidence=1.0,
                        # Enhanced relationship fields
                        relationship_type="primary",
                        relationship_category="amazon_affiliate",
                        margin_opportunity="affiliate_only",
                        revenue_type="affiliate_commission",
                        affiliate_links=[affiliate_link] if affiliate_link else []
                    )
                    result._source_product = amazon_product
                    results.append(result)
                    debug_logger.info(f"✅ Found existing Amazon product: {amazon_product.name}")
                else:
                    # Create placeholder Amazon product
                    result = ProductSearchResult(
                        id=f"amazon_{asin}",
                        title=f"Amazon Product {asin}",
                        name=f"Amazon Product {asin}",
                        part_number=asin,
                        description=f"Amazon product with ASIN {asin}",
                        asin=asin,
                        is_amazon_product=True,
                        is_alternative=False,
                        match_type="placeholder_asin",
                        match_confidence=1.0,
                        # Enhanced relationship fields
                        relationship_type="primary",
                        relationship_category="amazon_affiliate",
                        margin_opportunity="affiliate_only",
                        revenue_type="affiliate_commission",
                        affiliate_links=[affiliate_link] if affiliate_link else []
                    )
                    results.append(result)
                    debug_logger.info(f"📝 Created placeholder Amazon product for ASIN: {asin}")
                
                # IMPORTANT FIX: For direct ASIN requests, ONLY find supplier alternatives
                # DO NOT trigger additional Amazon searches or create future product records
                debug_logger.info(f"🔍 ASIN SEARCH: Looking for supplier alternatives only (no additional Amazon searches)")
                
                # Find supplier alternatives using INTERNAL inventory search only
                try:
                    # Use a simplified search term based on what we know
                    search_term_for_alternatives = ""
                    
                    if name:
                        # Extract basic product type from the provided name
                        name_lower = name.lower()
                        if any(laptop_term in name_lower for laptop_term in ['laptop', 'notebook', 'macbook', 'surface', 'thinkpad']):
                            search_term_for_alternatives = "laptop"
                        elif any(monitor_term in name_lower for monitor_term in ['monitor', 'display', 'screen']):
                            search_term_for_alternatives = "monitor"
                        elif any(desktop_term in name_lower for desktop_term in ['desktop', 'pc', 'computer']):
                            search_term_for_alternatives = "desktop"
                        elif any(keyboard_term in name_lower for keyboard_term in ['keyboard', 'kb']):
                            search_term_for_alternatives = "keyboard"
                        elif any(mouse_term in name_lower for mouse_term in ['mouse', 'mice']):
                            search_term_for_alternatives = "mouse"
                        else:
                            # Use first meaningful word from product name
                            words = name.split()
                            for word in words:
                                if len(word) > 3 and word.lower() not in ['the', 'and', 'with', 'for']:
                                    search_term_for_alternatives = word
                                    break
                    
                    if search_term_for_alternatives:
                        debug_logger.info(f"🔍 Searching internal inventory for '{search_term_for_alternatives}' alternatives")
                        
                        # Use ONLY internal inventory search - no external searches
                        internal_alternatives = self._search_internal_inventory_static(
                            part_number=None, 
                            name=search_term_for_alternatives
                        )
                        
                        # Add only supplier alternatives (not Amazon products)
                        for item in internal_alternatives:
                            if not item.is_amazon_product and item.is_alternative:
                                results.append(item)
                                debug_logger.info(f"✅ Added supplier alternative: {item.name}")
                    else:
                        debug_logger.info(f"⚠️ No search term extracted for alternatives")
                        
                except Exception as e:
                    debug_logger.error(f"❌ Error finding supplier alternatives: {e}")
                
                debug_logger.info(f"🎯 ASIN SEARCH COMPLETE: {len(results)} results (no search tasks triggered)")
                return results
            
            # PRIORITY 2: Part Number Search (CDW, Staples, Microsoft, etc.)
            elif partNumber:
                debug_logger.info(f"🎯 Multi-Site Part Number Search: {partNumber}")
                
                # SMART FIX: Check if partNumber is actually an Amazon ASIN
                # ASIN format: 10 characters, alphanumeric, starts with B
                import re
                if re.match(r'^B[A-Z0-9]{9}$', partNumber):
                    debug_logger.info(f"🧠 DETECTED: partNumber '{partNumber}' is actually an ASIN! Redirecting to ASIN flow...")
                    return self.resolve_unifiedProductSearch(info, asin=partNumber, name=name, url=url)
                
                return self._handle_non_amazon_product_search_static(partNumber=partNumber, name=name)
            
            # PRIORITY 3: Name Search (Universal Multi-Site)
            elif name:
                debug_logger.info(f"🎯 Universal Name Search: {name}")
                return self._handle_non_amazon_product_search_static(name=name, partNumber=partNumber)
            
            # PRIORITY 4: URL Parsing
            elif url:
                debug_logger.info(f"🎯 URL Parsing: {url}")
                # Extract retailer-specific identifiers from URL
                import re
                
                # Amazon ASIN extraction
                asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
                if asin_match:
                    extracted_asin = asin_match.group(1)
                    debug_logger.info(f"🔍 Extracted Amazon ASIN from URL: {extracted_asin}")
                    return self.resolve_unifiedProductSearch(info, asin=extracted_asin)
                
                debug_logger.info(f"⚠️  Could not extract product ID from URL: {url}")
                return []
            
            else:
                debug_logger.info("❌ No search parameters provided")
                return []
                
        except Exception as e:
            debug_logger.error(f"❌ Unified search error: {e}", exc_info=True)
            return []
    
    def resolve_unified_product_search(self, info, asin=None, part_number=None, name=None, url=None):
        """snake_case alias for unified search"""
        return self.resolve_unifiedProductSearch(info, asin, part_number, name, url)
    
    def resolve_debug_asin_lookup(self, info, asin):
        """Simple debug endpoint to check what's happening with ASIN lookup"""
        
        results = []
        
        # Check affiliate link
        try:
            affiliate_link = ensure_affiliate_link_exists(asin)
            if affiliate_link:
                results.append(f"✅ Affiliate Link: ID={affiliate_link.id}, URL={affiliate_link.affiliate_url[:30] if affiliate_link.affiliate_url else '(empty)'}...")
            else:
                results.append("❌ No affiliate link found")
        except Exception as e:
            results.append(f"❌ Affiliate link error: {str(e)}")
        
        # Check Amazon product
        try:
            amazon_product = get_amazon_product_by_asin(asin)
            if amazon_product:
                results.append(f"✅ Amazon Product: ID={amazon_product.id}, Name='{amazon_product.name[:50]}...'")
            else:
                results.append("❌ No Amazon product found")
        except Exception as e:
            results.append(f"❌ Amazon product error: {str(e)}")
        
        return " | ".join(results)
    
    @staticmethod
    def _handle_non_amazon_product_search_static(partNumber=None, name=None):
        """
        UNIVERSAL REVENUE STRATEGY for non-Amazon products
        
        Implements the 4-step revenue waterfall:
        1. Try internal inventory first (highest margin)
        2. CONDITIONAL Amazon search (only if needed)
        3. Find relevant accessories (cross-sell opportunities)  
        4. Create product records for future monetization
        """
        debug_logger.info(f"🌐 NON-AMAZON UNIVERSAL SEARCH: partNumber='{partNumber}', name='{name}'")
        
        results = []
        
        # STEP 1: Try Internal Inventory First (Highest Margin)
        internal_results = ProductQuery._search_internal_inventory_static(partNumber, name)
        results.extend(internal_results)
        
        # CRITICAL FIX: Only trigger Amazon search if we don't have good existing options with affiliate offers
        should_search_amazon = True
        existing_affiliate_products = 0
        
        for result in internal_results:
            # Count products that already have affiliate links/offers
            if hasattr(result, 'affiliate_links') and result.affiliate_links:
                existing_affiliate_products += 1
            elif hasattr(result, 'offers') and result.offers:
                # Check if any offers are affiliate offers
                for offer in result.offers:
                    if hasattr(offer, 'offer_type') and offer.offer_type == 'affiliate':
                        existing_affiliate_products += 1
                        break
        
        # SMART LOGIC: Don't search Amazon if we already have 2+ products with affiliate opportunities
        if existing_affiliate_products >= 2:
            should_search_amazon = False
            debug_logger.info(f"✅ SKIPPING Amazon search: Found {existing_affiliate_products} products with existing affiliate opportunities")
        elif len(internal_results) >= 5:
            should_search_amazon = False
            debug_logger.info(f"✅ SKIPPING Amazon search: Found {len(internal_results)} internal products (sufficient options)")
        else:
            debug_logger.info(f"🔍 CONDITIONAL Amazon search: Only {existing_affiliate_products} affiliate products, {len(internal_results)} total - searching for more options")
        
        # STEP 2: CONDITIONAL Amazon Search (only if needed)
        if should_search_amazon:
            debug_logger.info(f"🔍 Triggering Amazon search for additional options...")
            amazon_results = ProductQuery._dynamic_amazon_search_static(name or partNumber)
            results.extend(amazon_results)
        
        # STEP 3: Find Relevant Accessories (Cross-sell Opportunities)
        accessory_results = ProductQuery._find_relevant_accessories_for_product_static(name or partNumber)
        results.extend(accessory_results)
        
        # STEP 4: Create Product Record for Future (Background task)
        ProductQuery._create_product_record_for_future_static(partNumber, name)
        
        debug_logger.info(f"🎯 UNIVERSAL SEARCH RESULTS: {len(results)} total opportunities (Amazon search: {'triggered' if should_search_amazon else 'skipped'})")
        return results
    
    @staticmethod
    def _search_internal_inventory_static(part_number=None, name=None):
        """Search internal inventory with intelligent brand/model matching"""
        debug_logger.info(f"🔍 INTELLIGENT INTERNAL SEARCH: part='{part_number}', name='{name}'")
        
        results = []
        primary_product_for_alternatives = None  # Track the main product for alternative searches
        
        # PRIORITY 1: Exact part number match (PRIMARY products)
        if part_number:
            debug_logger.info(f"🔍 PRIORITY 1: Exact part number search...")
            exact_matches = Product.objects.filter(
                part_number__iexact=part_number
            ).select_related('manufacturer')[:3]
            
            for product in exact_matches:
                # Track the first match for alternative searches
                if not primary_product_for_alternatives:
                    primary_product_for_alternatives = product
                
                # Determine if this is an Amazon product or supplier product
                is_amazon_product = False
                
                # Check if product has Amazon characteristics
                if hasattr(product, 'main_image') and product.main_image:
                    if 'amazon.com' in product.main_image or 'images-amazon.com' in product.main_image:
                        is_amazon_product = True
                
                # Check for existing Amazon affiliate links
                existing_amazon_links = list(AffiliateLink.objects.filter(
                    product=product, 
                    platform='amazon'
                ))
                
                result = ProductSearchResult(
                    id=product.id,
                    name=product.name,
                    part_number=product.part_number,
                    description=product.description,
                    main_image=product.main_image,
                    manufacturer=product.manufacturer,
                    is_amazon_product=is_amazon_product,
                    is_alternative=False,  # Exact matches are primary, not alternatives
                    match_type="exact_part_number",
                    match_confidence=0.95,
                    relationship_type="primary",
                    relationship_category="exact_match",
                    margin_opportunity="high" if not is_amazon_product else "affiliate_only",
                    revenue_type="product_sale" if not is_amazon_product else "affiliate_commission",
                    offers=list(Offer.objects.filter(product=product).select_related('vendor')),
                    affiliate_links=existing_amazon_links
                )
                result._source_product = product
                results.append(result)
                
            debug_logger.info(f"✅ Found {len(exact_matches)} exact part number matches")
        
        # Additional logic for alternatives...
        # (Rest of the search logic follows similar pattern)
        
        debug_logger.info(f"🎯 INTELLIGENT SEARCH COMPLETE: {len(results)} results")
        return results
    
    @staticmethod
    def _dynamic_amazon_search_static(search_term):
        """Dynamic Amazon search with real-time affiliate link creation via Puppeteer worker"""
        debug_logger.info(f"🔍 REAL Amazon search for '{search_term}'")
        
        if not search_term or len(search_term.strip()) < 2:
            debug_logger.warning("Search term too short, skipping Amazon search")
            return []
        
        results = []
        
        try:
            # Trigger the Amazon search task
            debug_logger.info(f"🎯 Triggering Amazon search: term='{search_term}', type='general'")
            task_id, success = generate_affiliate_url_from_search(search_term, 'general')
            
            if success:
                debug_logger.info(f"✅ Amazon search task queued: {task_id}")
                
                # Create a placeholder result that indicates search is in progress
                placeholder_result = ProductSearchResult(
                    id=f"amazon_search_pending_{task_id}",
                    title=f"Amazon Search for '{search_term}' (Processing...)",
                    name=f"Amazon Search for '{search_term}' (Processing...)",
                    part_number=task_id,  # Use task_id as part number for tracking
                    description=f"Searching Amazon for products matching '{search_term}'. This may take a few moments...",
                    asin=f"SEARCH_{task_id}",
                    is_amazon_product=True,
                    is_alternative=True,
                    match_type="amazon_search_pending",
                    match_confidence=0.9,
                    relationship_type="equivalent",
                    relationship_category="amazon_search_alternative",
                    margin_opportunity="affiliate_only",
                    revenue_type="affiliate_commission",
                    price="Search in progress...",
                    availability=f"Amazon search task: {task_id}"
                )
                results.append(placeholder_result)
                
                debug_logger.info(f"🔍 Amazon search placeholder created with task_id: {task_id}")
                
            else:
                debug_logger.error(f"❌ Failed to queue Amazon search task")
                
        except Exception as e:
            debug_logger.error(f"❌ Error in dynamic Amazon search: {str(e)}", exc_info=True)
        
        debug_logger.info(f"🎯 Dynamic Amazon search completed: {len(results)} results")
        return results
    
    @staticmethod
    def _find_relevant_accessories_for_product_static(product_name):
        """Find relevant accessories from internal inventory for cross-sell opportunities"""
        debug_logger.info(f"🎯 ACCESSORIES SEARCH for: {product_name}")
        
        if not product_name:
            return []
        
        results = []
        # Implementation for finding accessories...
        
        debug_logger.info(f"🎯 Found {len(results)} relevant accessories")
        return results
    
    @staticmethod
    def _create_product_record_for_future_static(part_number, name):
        """Create a product record for future monetization opportunities"""
        try:
            debug_logger.info(f"📝 FUTURE PRODUCT: Queuing creation for part='{part_number}', name='{name}'")
            
            # Queue the task asynchronously
            task_data = {
                'part_number': part_number,
                'name': name,
                'source': 'chrome_extension_universal_search',
                'timestamp': timezone.now().isoformat()
            }
            
            # Use Django Q to queue the task
            async_task(
                'products.tasks.create_future_product_record',
                task_data,
                group='future_products',
                timeout=300
            )
            
            debug_logger.info(f"✅ Future product creation queued successfully")
            
        except Exception as e:
            debug_logger.error(f"❌ Error queuing future product creation: {e}")

# Helper functions
def get_redis_connection():
    """Helper to get standardized Redis connection kwargs"""
    if 'REDISCLOUD_URL' in os.environ:
        url = urlparse(os.environ['REDISCLOUD_URL'])
        return {
            'host': url.hostname,
            'port': url.port,
            'password': url.password,
            'decode_responses': True
        }
    else:
        redis_kwargs = {
            'host': getattr(settings, 'REDIS_HOST', 'localhost'),
            'port': getattr(settings, 'REDIS_PORT', 6379),
            'decode_responses': True
        }
        if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
            redis_kwargs['password'] = settings.REDIS_PASSWORD
        return redis_kwargs

def ensure_product_has_amazon_affiliate_link(product):
    """Check if a product has an Amazon affiliate link, and create one if it doesn't"""
    # Implementation...
    return []

def extract_search_terms(search_text):
    """Extract meaningful search terms from Amazon product names"""
    # Implementation...
    return {}

def find_product_candidates(search_terms):
    """Find potential product matches using various strategies"""
    # Implementation...
    return []

def score_and_select_best_match(search_text, candidates):
    """Score candidates and return the best match"""
    # Implementation...
    return None

def handle_affiliate_link_for_asin(product, asin, url):
    """Handle affiliate link creation/retrieval for a product and ASIN"""
    # Implementation...
    return None

def ensure_affiliate_link_exists(asin):
    """Always ensure we have an affiliate link for this ASIN"""
    try:
        # First, check if affiliate link already exists
        existing_link = AffiliateLink.objects.filter(
            platform='amazon',
            platform_id=asin
        ).first()
        
        if existing_link:
            debug_logger.info(f"✅ EXISTING affiliate link found for ASIN {asin}: {existing_link.affiliate_url}")
            return existing_link
        
        # If no existing link, create a new one
        debug_logger.info(f"🔄 Creating NEW affiliate link for ASIN: {asin}")
        
        # We need to trigger the affiliate link creation task
        # But first check if we already have a product for this ASIN
        from affiliates.tasks import generate_standalone_amazon_affiliate_url
        
        task_id, success = generate_standalone_amazon_affiliate_url(asin)
        
        if success:
            debug_logger.info(f"✅ Affiliate link creation task queued: {task_id}")
            
            # Return a placeholder affiliate link object
            class PlaceholderAffiliateLink:
                def __init__(self, asin):
                    self.id = f"pending_{asin}"
                    self.platform = 'amazon'
                    self.platform_id = asin
                    self.affiliate_url = ''  # Empty until generated
                    
            return PlaceholderAffiliateLink(asin)
        else:
            debug_logger.error(f"❌ Failed to queue affiliate link creation for ASIN: {asin}")
            return None
            
    except Exception as e:
        debug_logger.error(f"❌ Error ensuring affiliate link exists for ASIN {asin}: {e}")
        return None

def get_amazon_product_by_asin(asin):
    """Find the Amazon product we created for this ASIN"""
    try:
        # Look for existing affiliate link with this ASIN
        affiliate_link = AffiliateLink.objects.filter(
            platform='amazon',
            platform_id=asin
        ).select_related('product').first()
        
        if affiliate_link and affiliate_link.product:
            debug_logger.info(f"✅ Found existing product via affiliate link: {affiliate_link.product.name}")
            return affiliate_link.product
        
        debug_logger.info(f"❌ No existing product found for ASIN: {asin}")
        return None
        
    except Exception as e:
        debug_logger.error(f"❌ Error finding Amazon product by ASIN {asin}: {e}")
        return None