import graphene
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from graphql import GraphQLError
from django.db.models import Q
from django.contrib.auth import get_user_model
import logging
import graphql_jwt
import jwt
from django.conf import settings
from django.db import models  # Make sure this import is present
import json  # For pretty-printing objects
from django_q.tasks import async_task  # Add this import
import redis
import traceback  # Add this import
from affiliates.tasks import generate_standalone_amazon_affiliate_url  # Add this import
from graphene import relay  # Add this import for relay
import uuid
from django.utils.text import slugify
import re
from collections import Counter
from functools import lru_cache
import nltk
from nltk.corpus import stopwords
from django_q.tasks import async_task
import json
import redis
import logging
from django.conf import settings
from urllib.parse import urlparse
import os
import datetime
from django.utils import timezone
from datetime import timedelta

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

# from .graphql.types.scalars import JSONScalar

# Import all models with clear namespacing
from products.models import Product as ProductModel
from products.models import Category as CategoryModel
from products.models import Manufacturer as ManufacturerModel
from offers.models import Offer as OfferModel
from vendors.models import Vendor as VendorModel
from affiliates.models import AffiliateLink as AffiliateLinkModel
from store.models import Cart, CartItem
from users.models import UserProfile

# Import GraphQL types separately
from .graphql.types.user import UserType
from .graphql.types.cart import CartType, CartItemType
from .graphql.types.product import ProductType, CategoryType, ManufacturerType
from .graphql.types.affiliate import AffiliateLinkType
from .graphql.types.user import UserProfileType
from .graphql.mutations.auth import AuthMutation
from .graphql.mutations.product import ProductMutation
from .graphql.mutations.affiliate import AffiliateMutation, CreateAmazonAffiliateLink
from .graphql.mutations.cart import CartMutation
from graphql_jwt.decorators import login_required
from graphql_jwt.middleware import JSONWebTokenMiddleware

# Import the GraphQL types from your types directory
from ecommerce_platform.graphql.types.affiliate import AffiliateLinkType
from ecommerce_platform.graphql.types.offer import OfferType
from django_q.tasks import async_task

from products.matching import ProductMatcher
from products.consumer_matching import get_consumer_focused_results  # New import


User = get_user_model()

logger = logging.getLogger(__name__)

# Create a custom debug logger that writes to a specific file
debug_logger = logging.getLogger('debug_search')
debug_logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
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
    affiliate_link = graphene.Field(AffiliateLinkType)
    needs_affiliate_generation = graphene.Boolean()
    message = graphene.String()

# Input Types
class ProductInput(graphene.InputObjectType):
    """Input type for product data from Chrome extension"""
    name = graphene.String()
    manufacturer = graphene.String()
    description = graphene.String()
    partNumber = graphene.String()
    mainImage = graphene.String()
    price = graphene.Float()
    sourceUrl = graphene.String()
    technicalDetails = graphene.JSONString()

class AmazonProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    description = graphene.String()
    part_number = graphene.String(required=True)
    manufacturer_name = graphene.String(required=True)
    asin = graphene.String(required=True)
    url = graphene.String(required=True)
    image = graphene.String()
    price = graphene.Float()
    category_name = graphene.String()

class CartItemInput(graphene.InputObjectType):
    offer_id = graphene.ID(required=True)
    quantity = graphene.Int(required=True)

class AffiliateLinkInput(graphene.InputObjectType):
    product_id = graphene.ID(required=True)
    platform = graphene.String(required=True)
    platform_id = graphene.String(required=True)
    original_url = graphene.String(required=True)

# First, ensure ProductType has a connection
class ProductType(DjangoObjectType):
    class Meta:
        model = ProductModel
        interfaces = (relay.Node, )  # This enables the connection
        filter_fields = {
            'name': ['exact', 'icontains', 'istartswith'],
            'part_number': ['exact', 'icontains'],
            # add other fields as needed
        }
        connection_class = relay.Connection
    
    # BACKWARD COMPATIBILITY: Chrome extension expects asin field
    asin = graphene.String()
    
    def resolve_asin(self, info):
        """
        Resolve ASIN from affiliate links if available
        Chrome extension expects this field for Amazon compatibility
        """
        # Check if product has Amazon affiliate link
        amazon_link = AffiliateLinkModel.objects.filter(
            product=self,
            platform='amazon'
        ).first()
        
        if amazon_link:
            return amazon_link.platform_id
        
        # Fallback: check if part_number looks like an ASIN (10 chars, alphanumeric)
        if self.part_number and len(self.part_number) == 10 and self.part_number.isalnum():
            return self.part_number
            
        return None

# Query Class
class Query(graphene.ObjectType):
    # Product queries
    product = graphene.Field(ProductType, id=graphene.ID(), part_number=graphene.String())
    products = graphene.Field(
        'ecommerce_platform.schema.ProductConnection',
        search=graphene.String(),
        categoryId=graphene.ID(),
        manufacturerId=graphene.ID(),
        limit=graphene.Int(),
        offset=graphene.Int()
    )
    
    # Category queries
    categories = graphene.List(CategoryType, parent_id=graphene.ID())
    category = graphene.Field(CategoryType, id=graphene.ID(required=True))
    
    # Manufacturer queries
    manufacturers = graphene.List(ManufacturerType)
    manufacturer = graphene.Field(ManufacturerType, id=graphene.ID(required=True))
    
    # Offer queries
    offers_by_product = graphene.List('ecommerce_platform.graphql.types.offer.Offer', product_id=graphene.ID(required=True))
    
    # Check if product exists
    product_exists = graphene.Field(
        ProductExistsResponse,
        part_number=graphene.String(required=True),
        asin=graphene.String(),
        url=graphene.String()
    )
    
    # Affiliate links
    affiliate_links = graphene.List(AffiliateLinkType, product_id=graphene.ID(required=True))
    
    # Cart
    cart = graphene.Field(CartType, id=graphene.ID(), session_id=graphene.String())
    
    # Add the featured products query
    featured_products = graphene.List(
        ProductType,
        limit=graphene.Int()
    )
    
    # Add the user query field
    user = graphene.Field(UserType, id=graphene.ID())
    users = graphene.List(UserType)  # Optional: get all users
    current_user = graphene.Field(UserType)
    
    # Add an authenticated version that bypasses the usual middleware
    me = graphene.Field(UserType, description="Get the authenticated user's information")
    
    # Add this endpoint for debugging
    current_user_debug = graphene.Field(UserType, description="Debug endpoint for user auth")
    
    # Change products_search to use relay.ConnectionField
    products_search = DjangoFilterConnectionField(
        ProductType,
        term=graphene.String(),  # Remove required=True for backward compatibility
        asin=graphene.String(),
        max_price=graphene.Float()
    )
    
    # New search queries
    search_by_asin = graphene.List(
        'ecommerce_platform.schema.ProductSearchResult', 
        asin=graphene.String(required=True),
        limit=graphene.Int(default_value=10)
    )
    
    search_by_part_number = graphene.List(
        'ecommerce_platform.schema.ProductSearchResult', 
        part_number=graphene.String(required=True),
        limit=graphene.Int(default_value=10)
    )
    
    search_by_name = graphene.List(
        'ecommerce_platform.schema.ProductSearchResult', 
        name=graphene.String(required=True),
        limit=graphene.Int(default_value=10)
    )
    
    # Add this to your Query class
    standalone_affiliate_url = graphene.Field(
        graphene.String,
        task_id=graphene.String(required=True)
    )
    
    # Add this field
    check_affiliate_status = graphene.Field(
        'ecommerce_platform.schema.AffiliateTaskStatus',
        task_id=graphene.String(required=True),
        description="Check the status of an affiliate link generation task"
    )
    
    # Add simple debug query
    debug_asin_lookup = graphene.Field(
        graphene.String,
        asin=graphene.String(required=True),
        description="Debug endpoint to check ASIN lookup"
    )
    
    # Add the unified search endpoint that the Chrome extension expects
    unified_product_search = graphene.List(
        'ecommerce_platform.schema.ProductSearchResult',
        asin=graphene.String(),
        part_number=graphene.String(),
        name=graphene.String(),
        url=graphene.String(),
        description="Unified search endpoint for Chrome extension"
    )
    
    # Add camelCase alias for Chrome extension compatibility
    unifiedProductSearch = graphene.List(
        'ecommerce_platform.schema.ProductSearchResult',
        asin=graphene.String(),
        partNumber=graphene.String(),
        name=graphene.String(),
        url=graphene.String(),
        description="Unified search endpoint for Chrome extension (camelCase)"
    )
    
    search_by_asin = graphene.List(
        'ecommerce_platform.schema.ProductSearchResult',
        asin=graphene.String(required=True),
        description="Search products using Amazon ASIN with enhanced matching"
    )
    
    # New consumer-focused search
    consumer_product_search = graphene.List(
        'ecommerce_platform.schema.ProductSearchResult',
        term=graphene.String(),
        asin=graphene.String(),
        description="Consumer-focused product search prioritizing Amazon for devices, supplier for accessories"
    )
    
    def resolve_featured_products(self, info, limit=None):
        """
        Resolver to get featured products based on featured flag
        """
        # First try to get products marked as featured
        queryset = ProductModel.objects.filter(status='active', is_featured=True)
        
        # If no featured products, fall back to newest products
        if queryset.count() == 0:
            queryset = ProductModel.objects.filter(status='active').order_by('-created_at')
        
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
    
    def resolve_product(self, info, id=None, part_number=None):
        """Find a single product by ID or part number"""
        product = None
        if id:
            product = ProductModel.objects.get(pk=id)
        elif part_number:
            product = ProductModel.objects.get(part_number=part_number)
        
        if product:
            # Ensure this product has an Amazon affiliate link if needed
            ensure_product_has_amazon_affiliate_link(product)
        
        return product
    
    def resolve_products(self, info, search=None, categoryId=None, manufacturerId=None, limit=None, offset=None):
        query = ProductModel.objects.all()
        
        if search:
            query = query.filter(
                Q(name__icontains=search) | 
                Q(description__icontains=search) |
                Q(part_number__icontains=search)
            )
        
        if categoryId:
            query = query.filter(categories__id=categoryId)
        
        if manufacturerId:
            query = query.filter(manufacturer_id=manufacturerId)
        
        total_count = query.count()
        
        if offset is not None:
            query = query[offset:]
        
        if limit is not None:
            query = query[:limit]
            
        return ProductConnection(
            total_count=total_count,
            items=list(query)
        )
    
    def resolve_categories(self, info, parent_id=None):
        if parent_id:
            return CategoryModel.objects.filter(parent_id=parent_id)
        return CategoryModel.objects.filter(parent__isnull=True)
    
    def resolve_category(self, info, id):
        return CategoryModel.objects.get(pk=id)
    
    def resolve_manufacturers(self, info):
        return ManufacturerModel.objects.all()
    
    def resolve_manufacturer(self, info, id):
        return ManufacturerModel.objects.get(pk=id)
    
    def resolve_offers_by_product(self, info, product_id):
        return OfferModel.objects.filter(product_id=product_id)
    
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
            product = ProductModel.objects.prefetch_related(
                'offers', 'offers__vendor', 'affiliate_links', 'manufacturer', 'categories'
            ).get(part_number__iexact=part_number)
            match_method = "exact_part_number"
            debug_logger.info(f"✅ Found by exact part number: {product.name}")
        except ProductModel.DoesNotExist:
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
            existing_links = AffiliateLinkModel.objects.filter(
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
                    message=f"Product found via {match_method}. Affiliate link {'found' if affiliate_link.affiliate_url else 'queued'}."
                    )
            
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
                    message=f"Product found via {match_method}. Affiliate link {'found' if affiliate_link.affiliate_url else 'queued'}."
                )
        
        return ProductExistsResponse(
                exists=False,
                product=None,
                affiliate_link=None,
                needs_affiliate_generation=False,
                message="Product not found in database"
            )

    def resolve_affiliate_links(self, info, product_id):
        return AffiliateLinkModel.objects.filter(product_id=product_id)
    
    def resolve_cart(self, info, id=None, session_id=None):
        if id:
            return Cart.objects.get(pk=id)
        
        if session_id:
            return Cart.objects.filter(session_id=session_id).first()
        
        # If user is authenticated, return their cart
        user = info.context.user
        if user.is_authenticated:
            return Cart.objects.filter(user=user).first()
        
        return None

    def resolve_user(self, info, id=None):
        logger.info(f"resolve_user called with id: {id}")
        if not info.context.user.is_authenticated:
            logger.warning("User not authenticated in resolve_user")
            return None
        
        # If no ID provided, use the current user's ID
        if id is None:
            logger.info(f"No ID provided, returning current user: {info.context.user.id}")
            return info.context.user
            
        # Only allow staff/admin to query other users
        if str(info.context.user.id) != id and not info.context.user.is_staff:
            logger.warning(f"User {info.context.user.id} tried to access user {id}")
            return None
            
        try:
            logger.info(f"Fetching user with ID: {id}")
            return User.objects.get(pk=id)
        except User.DoesNotExist:
            logger.warning(f"User with ID {id} does not exist")
            return None
    
    def resolve_users(self, info):
        # Only staff/admin can query all users
        if not info.context.user.is_authenticated or not info.context.user.is_staff:
            return User.objects.none()
        return User.objects.all()
    
    def resolve_current_user(self, info):
        logger.info(f"resolve_current_user called, authenticated: {info.context.user.is_authenticated}")
        if info.context.user.is_authenticated:
            logger.info(f"Returning current user: {info.context.user.id}")
            return info.context.user
        logger.warning("User not authenticated in resolve_current_user")
        return None

    def resolve_me(self, info):
        user = info.context.user
        if user.is_anonymous:
            return None
        return user

    def resolve_current_user_debug(self, info):
        request = info.context
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        logger.info(f"🔍 Debug query called with auth header: {auth_header[:15]}...")
        
        if not auth_header.startswith('JWT '):
            logger.warning("🔍 No JWT in header")
            return None
            
        token = auth_header.split(' ')[1]
        logger.info(f"🔍 Found token: {token[:10]}...")
        
        # Try manual decode
        try:
            import jwt
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=['HS256'],
                options={'verify_signature': True}
            )
            logger.info(f"🔍 Successfully decoded: {payload}")
            
            # Get user directly
            user_id = payload.get('user_id')
            try:
                user = User.objects.get(id=user_id) 
                logger.info(f"🔍 Found user: {user.email}")
                return user
            except User.DoesNotExist:
                logger.warning(f"🔍 User {user_id} not found")
                return None
        except Exception as e:
            logger.error(f"🔍 Error decoding: {str(e)}")
            return None

    def resolve_products_search(self, info, term=None, asin=None, max_price=None, **kwargs):
        """
        Complete implementation for Chrome extension product search with affiliate link handling
        
        PRIORITY ORDER:
        1. ALWAYS include original Amazon product with affiliate link (from recent ProductExists request)
        2. ALSO include database alternatives with supplier offers
        """
        debug_logger.info(f"=== ENHANCED PRODUCT SEARCH START ===")
        debug_logger.info(f"Request: term='{term}', asin='{asin}', max_price={max_price}")
        
        # If no term provided, return empty result (backward compatibility)
        if not term:
            debug_logger.warning(f"⚠️ No search term provided, returning empty results")
            return ProductModel.objects.none()
        
        # FIND THE ORIGINAL AMAZON PRODUCT: Check recent ProductExists requests
        original_amazon_product = None
        original_asin = asin  # Use provided ASIN if available
        
        if not original_asin:
            # Strategy: Check cached ASIN from recent ProductExists requests
            try:
                import redis
                redis_kwargs = get_redis_connection()
                r = redis.Redis(**redis_kwargs)
                
                # Try different variations of the search term
                cache_keys = [
                    f"recent_asin:{term.lower().replace(' ', '_')}",
                    f"recent_asin:{term.lower()}",
                    f"recent_asin:{term.replace(' ', '_').lower()}"
                ]
                
                for cache_key in cache_keys:
                    cached_asin = r.get(cache_key)
                    if cached_asin:
                        original_asin = cached_asin
                        debug_logger.info(f"💾 Found cached ASIN '{original_asin}' for term '{term}'")
                        break
                        
                if not original_asin:
                    debug_logger.info(f"💾 No cached ASIN found for term '{term}'")
                        
            except Exception as e:
                debug_logger.warning(f"⚠️ Could not check cached ASIN: {str(e)}")
        
        # If we have an ASIN, ensure we get the Amazon product with affiliate link
        if original_asin:
            debug_logger.info(f"🔗 Processing original Amazon product: ASIN {original_asin}")
            
            try:
                # Ensure we have an affiliate link for this ASIN
                affiliate_link = ensure_affiliate_link_exists(original_asin)
                debug_logger.info(f"🔗 Affiliate link: {'✅ Found' if affiliate_link and affiliate_link.affiliate_url else '⏳ Pending'}")
                
                # Try to find our Amazon product for this ASIN
                if not original_amazon_product:
                    original_amazon_product = get_amazon_product_by_asin(original_asin)
                
                if original_amazon_product:
                    debug_logger.info(f"📦 Original Amazon product: {original_amazon_product.name}")
                else:
                    debug_logger.warning(f"❌ No Amazon product found for ASIN: {original_asin}")
                    
            except Exception as e:
                debug_logger.error(f"❌ Error handling original Amazon product: {str(e)}")

        # FIND DATABASE ALTERNATIVES: Search for matching database products
        debug_logger.info(f"🔍 Searching for database alternatives matching term: '{term}'")
        
        # Start with all active products
        qs = ProductModel.objects.filter(status='active').order_by('name')
        
        # Exclude the original Amazon product from alternatives (avoid duplicates)
        if original_amazon_product:
            qs = qs.exclude(id=original_amazon_product.id)
        
        # Search by product name/description/part number
        if term:
            # Try multiple search strategies:
            # 1. Check if term contains a part number in parentheses
            import re
            paren_matches = re.findall(r'\(([A-Za-z0-9\-_]+)\)', term)
            if paren_matches:
                part_number_candidate = paren_matches[0]
                debug_logger.info(f"📝 Extracted potential part number: {part_number_candidate}")
                
                # Try exact part number match first
                part_match = qs.filter(part_number__iexact=part_number_candidate)
                if part_match.exists():
                    debug_logger.info(f"🎯 Found exact part number match!")
                    qs = part_match
                else:
                    # Fall back to name search
                    qs = qs.filter(
                        Q(name__icontains=term) | 
                        Q(description__icontains=term) |
                        Q(part_number__icontains=term)
                    )
            else:
                # Regular text search
                qs = qs.filter(
                    Q(name__icontains=term) | 
                    Q(description__icontains=term) |
                    Q(part_number__icontains=term)
                )
        
        # Apply price filter to database alternatives only
        if max_price is not None:
            from decimal import Decimal
            try:
                max_price_decimal = Decimal(str(max_price))
                qs = qs.filter(offers__selling_price__lte=max_price_decimal).distinct()
                debug_logger.info(f"💰 Applied price filter to database alternatives: <= ${max_price}")
            except (ValueError, TypeError):
                debug_logger.warning(f"⚠️ Invalid price filter: {max_price}")
        
        # COMBINE RESULTS: Original Amazon product FIRST, then database alternatives
        final_products = []
        
        # 1. Add original Amazon product FIRST (with affiliate link)
        if original_amazon_product:
            final_products.append(original_amazon_product)
            debug_logger.info(f"✅ Added original Amazon product: {original_amazon_product.name}")
        
        # 2. Add database alternatives (with supplier offers)
        database_alternatives = list(qs)
        final_products.extend(database_alternatives)
        
        products_found = len(final_products)
        amazon_count = 1 if original_amazon_product else 0
        alternatives_count = len(database_alternatives)
        
        debug_logger.info(f"📊 Found {amazon_count} original Amazon + {alternatives_count} alternatives = {products_found} total products")
        
        # Log response details for debugging
        if products_found > 0:
            debug_logger.info(f"📋 Product results:")
            for i, product in enumerate(final_products[:5]):  # Log first 5
                is_original_amazon = (product == original_amazon_product)
                offers = OfferModel.objects.filter(product=product)
                affiliate_links = AffiliateLinkModel.objects.filter(product=product)
                debug_logger.info(f"  {i+1}. {'[ORIGINAL AMAZON]' if is_original_amazon else '[ALTERNATIVE]'} {product.name} | Part: {product.part_number} | Offers: {offers.count()} | Links: {affiliate_links.count()}")
        
        # Log final results
        result_description = []
        if original_amazon_product:
            result_description.append(f"Original Amazon (ASIN: {original_asin})")
        if alternatives_count > 0:
            result_description.append(f"{alternatives_count} alternatives")
        
        debug_logger.info(f"🎯 RESULT: Returning {products_found} products ({', '.join(result_description)})")
        debug_logger.info(f"=== ENHANCED PRODUCT SEARCH END ===")
        
        # Return a queryset-like object that Django can handle
        if final_products:
            product_ids = [p.id for p in final_products]
            # For DjangoFilterConnectionField, we need to return a proper queryset
            # Create a custom ordering to preserve original-first order
            if product_ids:
                from django.db.models import Case, When, IntegerField
                order_cases = [When(id=product_id, then=i) for i, product_id in enumerate(product_ids)]
                return ProductModel.objects.filter(id__in=product_ids).annotate(
                    custom_order=Case(*order_cases, output_field=IntegerField())
                ).order_by('custom_order')
            else:
                return ProductModel.objects.filter(id__in=product_ids)
        else:
            return ProductModel.objects.none()

    def resolve_search_by_asin(self, info, asin):
        """Enhanced ASIN search with supplier-focused matching (No Amazon API)"""
        try:
            debug_logger.info(f"🔍 ASIN Search for: {asin}")
            
            # CORE BUSINESS LOGIC: Always ensure affiliate link exists for ASIN
            affiliate_link = ensure_affiliate_link_exists(asin)
            debug_logger.info(f"🔗 Affiliate link: {'✅ Found' if affiliate_link and affiliate_link.affiliate_url else '⏳ Pending/Created'}")
            
            # Try to find existing Amazon product for this ASIN
            amazon_product = get_amazon_product_by_asin(asin)
            
            results = []
            
            if amazon_product:
                # We have an Amazon product in our database
                debug_logger.info(f"📦 Found Amazon product: {amazon_product.name}")
                
                # Ensure it has the affiliate link
                if affiliate_link and affiliate_link.product != amazon_product:
                    affiliate_link.product = amazon_product
                    affiliate_link.save()
                
                result = ProductSearchResult(
                    id=amazon_product.id,
                    title=amazon_product.name,
                    name=amazon_product.name,
                    price="See Amazon for pricing",
                    currency='USD',
                    availability='Available on Amazon',
                    product_url=f'https://amazon.com/dp/{asin}',
                    image_url=amazon_product.main_image or "",
                    asin=asin,
                    match_confidence=0.95,
                    match_type='amazon_product_asin_match',
                    is_amazon_product=True,
                    is_alternative=False,
                    part_number=amazon_product.part_number,
                    manufacturer=amazon_product.manufacturer,
                    description=amazon_product.description or ""
                )
                result._source_product = amazon_product
                results.append(result)
                
            else:
                # No Amazon product found, create a placeholder with affiliate link
                debug_logger.info(f"📦 No Amazon product found, creating placeholder")
                
                result = ProductSearchResult(
                    title=f'Amazon Product (ASIN: {asin})',
                    price='See Amazon for pricing',
                    currency='USD',
                    availability='Available on Amazon',
                    product_url=f'https://amazon.com/dp/{asin}',
                    image_url='',
                    asin=asin,
                    match_confidence=0.9,
                    match_type='amazon_asin_placeholder',
                    is_amazon_product=True,
                    is_alternative=False
                )
                result._source_product = None
                results.append(result)
            
            # Use consumer-focused matching to find supplier alternatives  
            consumer_results = get_consumer_focused_results("", asin)
            
            # Add supplier alternatives (but Amazon product should be first)
            for item in consumer_results['results']:
                if not item['isAmazonProduct']:  # Only add supplier products as alternatives
                    product = item['product']
                    
                    result = ProductSearchResult(
                        id=product.id,
                        title=product.name,
                        name=product.name,
                        price="Contact for pricing",
                        currency="USD",
                        availability="Available",
                        product_url="",
                        image_url=product.main_image or "",
                        asin="",
                        match_confidence=item['matchConfidence'],
                        match_type=item['matchType'],
                        is_amazon_product=False,
                        is_alternative=True,
                        part_number=product.part_number,
                        manufacturer=product.manufacturer,
                        description=product.description or ""
                    )
                    result._source_product = product
                    results.append(result)
            
            debug_logger.info(f"🎯 Returning {len(results)} results (Amazon primary + {len(results)-1} alternatives)")
            return results
            
        except Exception as e:
            debug_logger.error(f"❌ Error in search_by_asin: {e}")
            print(f"Error in search_by_asin: {e}")
            
            # Even on error, ensure affiliate link exists
            try:
                ensure_affiliate_link_exists(asin)
            except:
                pass
                
            return []
    
    def resolve_consumer_product_search(self, info, term=None, asin=None):
        """Consumer-focused product search (No Amazon API version)"""
        if not term and not asin:
            return []
        
        try:
            # Use the new consumer-focused matching
            consumer_results = get_consumer_focused_results(term or "", asin)
            
            # Convert to GraphQL format
            results = []
            for item in consumer_results['results']:
                product = item['product']
                
                if item['isAmazonProduct']:
                    # Amazon placeholder - affiliate link handled by puppeteer
                    result = ProductSearchResult(
                        title=product.get('title', ''),
                        price=product.get('price', 'See Amazon for pricing'),
                        currency='USD',
                        availability=product.get('availability', 'Available on Amazon'),
                        product_url=product.get('detail_page_url', ''),
                        image_url='',  # No image access without API
                        asin=product.get('asin', ''),
                        match_confidence=item['matchConfidence'],
                        match_type=item['matchType'],
                        is_amazon_product=True,
                        is_alternative=item['isAlternative']
                    )
                    # No source product for Amazon placeholders
                    result._source_product = None
                else:
                    # Supplier product with full data
                    result = ProductSearchResult(
                        id=product.id,
                        title=product.name,
                        name=product.name,
                        price="Contact for pricing", 
                        currency="USD",
                        availability="Available",
                        product_url="",
                        image_url=product.main_image or "",
                        asin="",
                        match_confidence=item['matchConfidence'],
                        match_type=item['matchType'],
                        is_amazon_product=False,
                        is_alternative=item['isAlternative'],
                        part_number=product.part_number,
                        manufacturer=product.manufacturer,
                        description=product.description or ""
                    )
                    # Set the source product for backward compatibility
                    result._source_product = product
                
                results.append(result)
            
            # Add fallback suggestion if available
            if consumer_results.get('amazonFallbackSuggestion') and not results:
                # Return a helpful suggestion result
                suggestion_result = ProductSearchResult(
                    title=f"Try searching Amazon for: {consumer_results['amazonFallbackSuggestion']}",
                    price="Search Amazon",
                    currency="USD",
                    availability="Suggestion",
                    product_url=f"https://amazon.com/s?k={consumer_results['amazonFallbackSuggestion'].replace(' ', '+')}",
                    image_url="",
                    asin="",
                    match_confidence=0.5,
                    match_type="amazon_search_suggestion",
                    is_amazon_product=False,
                    is_alternative=False
                )
                # No source product for suggestions
                suggestion_result._source_product = None
                results.append(suggestion_result)
            
            return results
            
        except Exception as e:
            print(f"Error in consumer_product_search: {e}")
            return []
    
    def resolve_unified_product_search(self, info, asin=None, part_number=None, name=None, url=None):
        """
        UNIFIED MULTI-RETAILER SEARCH
        
        This is the main entry point for Chrome extension searches across:
        - Amazon (ASIN)
        - Best Buy (SKU)  
        - Staples (Item Number)
        - CDW (Part Number)
        - Newegg (Item Number)
        
        Priority: ASIN -> partNumber -> name -> URL parsing
        """
        try:
            debug_logger.info(f"🔍 Unified Search - ASIN: {asin}, Part: {part_number}, Name: {name}, URL: {url}")
            
            # PRIORITY 1: ASIN Search (Amazon)
            if asin:
                debug_logger.info(f"🎯 Amazon ASIN Search: {asin}")
                
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
                
                # Find supplier alternatives using consumer matching
                try:
                    from products.consumer_matching import get_consumer_focused_results
                    consumer_results = get_consumer_focused_results("", asin)
                    
                    for item in consumer_results['results']:
                        if not item['isAmazonProduct']:  # Only add supplier alternatives
                            product = item['product']
                            result = ProductSearchResult(
                                id=product.id,
                                name=product.name,
                                part_number=product.part_number,
                                description=product.description,
                                main_image=product.main_image,
                                manufacturer=product.manufacturer,
                                is_amazon_product=False,
                                is_alternative=True,
                                match_type=item.get('matchType', 'supplier_alternative'),
                                match_confidence=item.get('matchConfidence', 0.7),
                                # Enhanced relationship fields
                                relationship_type=item.get('relationshipType', 'equivalent'),
                                relationship_category=item.get('relationshipCategory', 'supplier_alternative'),
                                margin_opportunity=item.get('marginOpportunity', 'medium'),
                                revenue_type=item.get('revenueType', 'product_sale'),
                                offers=list(OfferModel.objects.filter(product=product).select_related('vendor')),
                                affiliate_links=list(AffiliateLinkModel.objects.filter(product=product))
                            )
                            result._source_product = product
                            results.append(result)
                    
                    debug_logger.info(f"🔍 Added {len([r for r in results if r.is_alternative])} supplier alternatives")
                    
                except Exception as e:
                    debug_logger.error(f"❌ Consumer matching error: {e}")
                
                return results
            
            # PRIORITY 2: Part Number Search (CDW, Staples, etc.)
            elif part_number:
                debug_logger.info(f"🎯 Part Number Search: {part_number}")
                return self.resolve_search_by_part_number(info, part_number)
            
            # PRIORITY 3: Name Search (Generic)
            elif name:
                debug_logger.info(f"🎯 Name Search: {name}")
                return self.resolve_search_by_name(info, name)
            
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
                
                # TODO: Add Best Buy, Staples, CDW URL parsing
                # Best Buy: /site/product-name/productId.p?skuId=XXXXXX
                # Staples: /product_XXXXXX
                # CDW: /product/product-name/XXXXXX
                
                debug_logger.info(f"⚠️  Could not extract product ID from URL: {url}")
                return []
            
            else:
                debug_logger.info("❌ No search parameters provided")
                return []
                
        except Exception as e:
            debug_logger.error(f"❌ Unified search error: {e}", exc_info=True)
            return []
    
    def resolve_unifiedProductSearch(self, info, asin=None, partNumber=None, name=None, url=None):
        """
        UNIFIED MULTI-RETAILER SEARCH (CHROME EXTENSION)
        
        Self-contained resolver for Chrome extension searches across:
        - Amazon (ASIN)
        - Best Buy (SKU)  
        - Staples (Item Number)
        - CDW (Part Number)
        - Newegg (Item Number)
        
        Priority: ASIN -> partNumber -> name -> URL parsing
        """
        try:
            debug_logger.info(f"🔍 Chrome Extension Unified Search - ASIN: {asin}, Part: {partNumber}, Name: {name}, URL: {url}")
            
            # PRIORITY 1: ASIN Search (Amazon)
            if asin:
                debug_logger.info(f"🎯 Amazon ASIN Search: {asin}")
                
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
                
                # Find supplier alternatives using consumer matching
                try:
                    from products.consumer_matching import get_consumer_focused_results
                    consumer_results = get_consumer_focused_results("", asin)
                    
                    for item in consumer_results['results']:
                        if not item['isAmazonProduct']:  # Only add supplier alternatives
                            product = item['product']
                            result = ProductSearchResult(
                                id=product.id,
                                name=product.name,
                                part_number=product.part_number,
                                description=product.description,
                                main_image=product.main_image,
                                manufacturer=product.manufacturer,
                                is_amazon_product=False,
                                is_alternative=True,
                                match_type=item.get('matchType', 'supplier_alternative'),
                                match_confidence=item.get('matchConfidence', 0.7),
                                # Enhanced relationship fields
                                relationship_type=item.get('relationshipType', 'equivalent'),
                                relationship_category=item.get('relationshipCategory', 'supplier_alternative'),
                                margin_opportunity=item.get('marginOpportunity', 'medium'),
                                revenue_type=item.get('revenueType', 'product_sale'),
                                offers=list(OfferModel.objects.filter(product=product).select_related('vendor')),
                                affiliate_links=list(AffiliateLinkModel.objects.filter(product=product))
                            )
                            result._source_product = product
                            results.append(result)
                    
                    debug_logger.info(f"🔍 Added {len([r for r in results if r.is_alternative])} supplier alternatives")
                    
                except Exception as e:
                    debug_logger.error(f"❌ Consumer matching error: {e}")
                
                return results
            
            # PRIORITY 2: Part Number Search (CDW, Staples, etc.)
            elif partNumber:
                debug_logger.info(f"🎯 Part Number Search: {partNumber}")
                
                # Direct part number search without calling other resolvers
                products = ProductModel.objects.filter(
                    part_number__icontains=partNumber
                ).select_related('manufacturer')[:10]
                
                results = []
                for product in products:
                    # Ensure each product has an Amazon affiliate link if needed
                    product_links = ensure_product_has_amazon_affiliate_link(product)
                    
                    # Get all offers for this product
                    product_offers = list(OfferModel.objects.filter(product=product).select_related('vendor'))
                    
                    # Create ProductSearchResult with backward compatibility
                    result = ProductSearchResult(
                        id=product.id,
                        name=product.name,
                        part_number=product.part_number,
                        description=product.description,
                        main_image=product.main_image,
                        manufacturer=product.manufacturer,
                        affiliate_links=product_links,
                        offers=product_offers,
                        is_amazon_product=False,
                        is_alternative=False,
                        match_type="exact_part_number",
                        match_confidence=0.9
                    )
                    # Set the source product for backward compatibility
                    result._source_product = product
                    results.append(result)
                
                return results
            
            # PRIORITY 3: Name Search (Generic)
            elif name:
                debug_logger.info(f"🎯 Name Search: {name}")
                
                # Split the search term into words for more flexible searching
                search_terms = name.split()
                query = ProductModel.objects.all().select_related('manufacturer')
                
                # Apply each search term as a filter
                for term in search_terms:
                    query = query.filter(name__icontains=term)
                
                products = query[:10]
                
                results = []
                for product in products:
                    # Ensure this product has an Amazon affiliate link if needed
                    product_links = ensure_product_has_amazon_affiliate_link(product)
                    
                    # Get all offers for this product
                    product_offers = list(OfferModel.objects.filter(product=product).select_related('vendor'))
                    
                    # Create ProductSearchResult with backward compatibility
                    result = ProductSearchResult(
                        id=product.id,
                        name=product.name,
                        part_number=product.part_number,
                        description=product.description,
                        main_image=product.main_image,
                        manufacturer=product.manufacturer,
                        affiliate_links=product_links,
                        offers=product_offers,
                        is_amazon_product=False,
                        is_alternative=False,
                        match_type="name_search",
                        match_confidence=0.8
                    )
                    # Set the source product for backward compatibility
                    result._source_product = product
                    results.append(result)
                
                return results
            
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
                    # Recursive call with extracted ASIN
                    return self.resolve_unifiedProductSearch(info, asin=extracted_asin)
                
                # TODO: Add Best Buy, Staples, CDW URL parsing
                # Best Buy: /site/product-name/productId.p?skuId=XXXXXX
                # Staples: /product_XXXXXX
                # CDW: /product/product-name/XXXXXX
                
                debug_logger.info(f"⚠️  Could not extract product ID from URL: {url}")
                return []
            
            else:
                debug_logger.info("❌ No search parameters provided")
                return []
                
        except Exception as e:
            debug_logger.error(f"❌ Unified search error: {e}", exc_info=True)
            return []
    
    def resolve_search_by_part_number(self, info, part_number, limit=10):
        """
        Find products by part number (case-insensitive search)
        """
        products = ProductModel.objects.filter(
            part_number__icontains=part_number
        ).select_related('manufacturer')[:limit]
        
        results = []
        for product in products:
            # Ensure each product has an Amazon affiliate link if needed
            product_links = ensure_product_has_amazon_affiliate_link(product)
            
            # Get all offers for this product
            product_offers = list(OfferModel.objects.filter(product=product).select_related('vendor'))
            
            # Create ProductSearchResult with backward compatibility
            result = ProductSearchResult(
                id=product.id,
                name=product.name,
                part_number=product.part_number,
                description=product.description,
                main_image=product.main_image,
                manufacturer=product.manufacturer,
                affiliate_links=product_links,
                offers=product_offers,
                is_amazon_product=False,
                is_alternative=False,
                match_type="exact_part_number",
                match_confidence=0.9
            )
            # Set the source product for backward compatibility
            result._source_product = product
            results.append(result)
            
        return results
    
    def resolve_search_by_name(self, info, name, limit=10):
        """
        Find products whose names contain words in the search query
        """
        # Split the search term into words for more flexible searching
        search_terms = name.split()
        query = ProductModel.objects.all().select_related('manufacturer')
        
        # Apply each search term as a filter
        for term in search_terms:
            query = query.filter(name__icontains=term)
        
        products = query[:limit]
        
        results = []
        for product in products:
            # Ensure this product has an Amazon affiliate link if needed
            product_links = ensure_product_has_amazon_affiliate_link(product)
            
            # Get all offers for this product
            product_offers = list(OfferModel.objects.filter(product=product).select_related('vendor'))
            
            # Create ProductSearchResult with backward compatibility
            result = ProductSearchResult(
                id=product.id,
                name=product.name,
                part_number=product.part_number,
                description=product.description,
                main_image=product.main_image,
                manufacturer=product.manufacturer,
                affiliate_links=product_links,
                offers=product_offers,
                is_amazon_product=False,
                is_alternative=False,
                match_type="name_search",
                match_confidence=0.8
            )
            # Set the source product for backward compatibility
            result._source_product = product
            results.append(result)
            
        return results

    def resolve_standalone_affiliate_url(self, info, task_id):
        """Get the status of a standalone affiliate URL generation task"""

        
        logger = logging.getLogger('affiliate_tasks')
        logger.info(f"Checking standalone affiliate URL for task_id: {task_id}")
        
        try:
            # Parse the REDISCLOUD_URL
            if 'REDISCLOUD_URL' in os.environ:
                url = urlparse(os.environ['REDISCLOUD_URL'])
                redis_kwargs = {
                    'host': url.hostname,
                    'port': url.port,
                    'password': url.password,
                    'decode_responses': True
                }
            else:
                # Fallback to local development settings
                redis_kwargs = {
                    'host': getattr(settings, 'REDIS_HOST', 'localhost'),
                    'port': getattr(settings, 'REDIS_PORT', 6379),
                    'decode_responses': True
                }
                # Only add password if it exists in settings
                if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
                    redis_kwargs['password'] = settings.REDIS_PASSWORD

            r = redis.Redis(**redis_kwargs)
            
            # Check if task is still pending
            asin = r.get(f"pending_standalone_task:{task_id}")
            if asin:
                logger.info(f"Task {task_id} is still pending")
                return json.dumps({
                    "status": "pending",
                    "message": "Task is still processing"
                })
            
            # Get the task status from Redis
            result = r.get(f"standalone_task_status:{task_id}")
            if not result:
                logger.info(f"No result found for task {task_id}")
                return json.dumps({
                    "status": "not_found",
                    "message": "Task not found or expired"
                })
            
            # Return the raw result, it's already JSON
            logger.info(f"Found result for task {task_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving standalone affiliate URL: {str(e)}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": str(e)
            })

    def resolve_check_affiliate_status(self, info, task_id):
        """
        Check the status of an affiliate link generation task
        """
        try:
            import redis
            import json
            from django.conf import settings
            
            # Get Redis connection
            redis_kwargs = get_redis_connection()
            r = redis.Redis(**redis_kwargs)
            
            # Check if task result exists
            task_status_json = r.get(f"standalone_task_status:{task_id}")
            
            if not task_status_json:
                # Check if task exists in Django Q
                from django_q.models import Task
                try:
                    task = Task.objects.get(id=task_id)
                    if task.success is None:
                        status = "pending"
                    elif task.success:
                        status = "completed"
                    else:
                        status = "failed"
                    
                    return AffiliateTaskStatus(
                        task_id=task_id,
                        status=status,
                        affiliate_url=None,
                        error=task.result if not task.success else None
                    )
                except Task.DoesNotExist:
                    return AffiliateTaskStatus(
                        task_id=task_id,
                        status="not_found",
                        affiliate_url=None,
                        error="Task not found"
                    )
            
            # Parse and return the result from Redis
            task_status = json.loads(task_status_json)
            
            return AffiliateTaskStatus(
                task_id=task_id,
                status=task_status.get('status', 'unknown'),
                affiliate_url=task_status.get('affiliate_url'),
                error=task_status.get('error')
            )
            
        except Exception as e:
            logger.error(f"Error checking affiliate task status: {e}")
            return AffiliateTaskStatus(
                task_id=task_id,
                status="error",
                affiliate_url=None,
                error=str(e)
            )

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

# Mutation Class
class CreateProduct(graphene.Mutation):
    class Arguments:
        input = ProductInput(required=True)
    
    product = graphene.Field(ProductType)
    
    @staticmethod
    def mutate(root, info, input):
        manufacturer = ManufacturerModel.objects.get(pk=input.manufacturer_id)
        
        # Create the product
        product = ProductType(
            name=input.name,
            description=input.description,
            manufacturer=manufacturer,
            part_number=input.part_number,
            specifications=input.specifications,
            weight=input.weight,
            dimensions=input.dimensions,
            main_image=input.main_image,
            additional_images=input.additional_images,
            status=input.status or 'active',
            slug=input.part_number.lower().replace(' ', '-')
        )
        product.save()
        
        # Add categories if provided
        if input.category_ids:
            for category_id in input.category_ids:
                category = CategoryModel.objects.get(pk=category_id)
                product.categories.add(category)
        
        return CreateProduct(product=product)

class UpdateProduct(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        input = ProductInput(required=True)
    
    product = graphene.Field(ProductType)
    
    @staticmethod
    def mutate(root, info, id, input):
        try:
            product = ProductType.objects.get(pk=id)
        except ProductType.DoesNotExist:
            raise GraphQLError(f"Product with ID {id} does not exist")
        
        # Update basic fields
        product.name = input.name
        if input.description is not None:
            product.description = input.description
        
        if input.manufacturer_id:
            product.manufacturer = ManufacturerModel.objects.get(pk=input.manufacturer_id)
        
        product.part_number = input.part_number
        
        if input.specifications is not None:
            product.specifications = input.specifications
        
        if input.weight is not None:
            product.weight = input.weight
        
        if input.dimensions is not None:
            product.dimensions = input.dimensions
        
        if input.main_image is not None:
            product.main_image = input.main_image
        
        if input.additional_images is not None:
            product.additional_images = input.additional_images
        
        if input.status is not None:
            product.status = input.status
        
        product.save()
        
        # Update categories if provided
        if input.category_ids:
            product.categories.clear()
            for category_id in input.category_ids:
                category = CategoryModel.objects.get(pk=category_id)
                product.categories.add(category)
        
        return UpdateProduct(product=product)

class CreateProductFromAmazon(graphene.Mutation):
    class Arguments:
        input = AmazonProductInput(required=True)
    
    product = graphene.Field(ProductType)
    
    @staticmethod
    def mutate(root, info, input):
        # Get or create manufacturer with a unique slug
        manufacturer_name = input.manufacturer_name
        
        try:
            # First try to find by exact name
            manufacturer = ManufacturerModel.objects.get(name__iexact=manufacturer_name)
        except ManufacturerModel.DoesNotExist:
            # Create new with a unique slug
            base_slug = slugify(manufacturer_name)
            unique_slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
            
            manufacturer = ManufacturerModel.objects.create(
                name=manufacturer_name,
                slug=unique_slug
            )
        
        # Create new product
        product = ProductModel(
            name=input.name,
            description=input.description,
            manufacturer=manufacturer,
            part_number=input.part_number,
            slug=f"{slugify(input.part_number)}-{uuid.uuid4().hex[:8]}",  # Unique product slug too
            main_image=input.image,
            status='active'
        )
        product.save()
        
        # Add to category if provided
        if input.category_name:
            category, created = CategoryModel.objects.get_or_create(
                name=input.category_name,
                defaults={
                    'slug': f"{slugify(input.category_name)}-{uuid.uuid4().hex[:8]}",
                    'is_visible': True
                }
            )
            product.categories.add(category)
        
        # Check if affiliate link already exists before creating
        existing_affiliate = AffiliateLinkModel.objects.filter(
            product=product,
            platform='amazon', 
            platform_id=input.asin
        ).first()

        if not existing_affiliate:
            # Create new affiliate link
            affiliate_link = AffiliateLinkModel(
                product=product,
                platform='amazon',
                platform_id=input.asin,
                original_url=input.url,
                affiliate_url='',
                is_active=True
            )
            affiliate_link.save()
            
            # Queue background task
            async_task('affiliates.tasks.generate_amazon_affiliate_url', affiliate_link.id, input.asin)
            debug_logger.info(f"🔗 Created new affiliate link for product {product.id}")
        else:
            debug_logger.info(f"✅ Affiliate link already exists for product {product.id} + ASIN {input.asin}")
        
        return CreateProductFromAmazon(product=product)

class CreateAffiliateLink(graphene.Mutation):
    class Arguments:
        input = AffiliateLinkInput(required=True)
    
    affiliate_link = graphene.Field(AffiliateLinkType)
    
    @staticmethod
    def mutate(root, info, input):
        try:
            product = ProductType.objects.get(pk=input.product_id)
            
            affiliate_link = AffiliateLinkModel(
                product=product,
                platform=input.platform,
                platform_id=input.platform_id,
                original_url=input.original_url,
                affiliate_url='',  # Will be populated later
                is_active=True
            )
            affiliate_link.save()
            
            return CreateAffiliateLink(affiliate_link=affiliate_link)
        except ProductType.DoesNotExist:
            raise GraphQLError(f"Product with ID {input.product_id} not found")
        except Exception as e:
            raise GraphQLError(str(e))

class CreateAmazonAffiliateLink(graphene.Mutation):
    class Arguments:
        asin = graphene.String(required=True)
        productId = graphene.String(required=True)
        currentUrl = graphene.String(required=False)
        productData = ProductInput(required=False)
    
    # Return fields that match the Chrome extension's expectations
    taskId = graphene.String()
    affiliateUrl = graphene.String()
    status = graphene.String()
    message = graphene.String()
    
    @staticmethod
    def mutate(root, info, asin, productId=None, currentUrl=None, productData=None):
        try:
            logger = logging.getLogger('affiliate_tasks')
            logger.info(f"CreateAmazonAffiliateLink called with: asin={asin}, productId={productId}, currentUrl={currentUrl}")
            
            if productData:
                logger.info(f"Product data: name={productData.name}, manufacturer={productData.manufacturer}")
                
                # Convert technicalDetails to JSONString if it's already a dict
                if hasattr(productData, 'technicalDetails') and isinstance(productData.technicalDetails, dict):
                    productData.technicalDetails = json.dumps(productData.technicalDetails)
            
            # Special handling for 'new_product' product_id from Chrome extension
            if productId == 'new_product' and productData:
                logger.info("New product creation requested")
                
                # Queue task to generate affiliate URL and create product
                logger.info(f"Queueing task to generate affiliate URL for ASIN: {asin}")
                url = productData.sourceUrl or f"https://www.amazon.com/dp/{asin}"
                task_id, success = generate_standalone_amazon_affiliate_url(asin)
                print("task_id", task_id)
                if not success:
                    return CreateAmazonAffiliateLink(
                        taskId=None,
                        affiliateUrl=None,
                        status="error",
                        message="Failed to queue task with puppeteer service"
                    )
                
                logger.info(f"Created task ID: {task_id}")
                
                # Store product data in Redis
                redis_kwargs = get_redis_connection()
                r = redis.Redis(**redis_kwargs)
                
                # Store all product data with the task_id
                product_data_dict = {
                    "asin": asin,
                    "name": productData.name,
                    "description": productData.description,
                    "mainImage": productData.mainImage,
                    "manufacturer": productData.manufacturer,
                    "partNumber": productData.partNumber or asin,
                    "price": productData.price,
                    "sourceUrl": productData.sourceUrl,
                    "technicalDetails": productData.technicalDetails
                }
                r.set(f"pending_product_data:{task_id}", json.dumps(product_data_dict), ex=86400)
                
                return CreateAmazonAffiliateLink(
                    taskId=task_id,
                    affiliateUrl="pending",
                    status="processing",
                    message="Affiliate link is being generated"
                )
            else:
                # Handle other cases
                logger.info(f"Using product ID: {productId}")
                
                url = currentUrl or f"https://www.amazon.com/dp/{asin}"
                task_id, success = generate_standalone_amazon_affiliate_url(asin)
                
                if not success:
                    return CreateAmazonAffiliateLink(
                        taskId=None,
                        affiliateUrl=None,
                        status="error",
                        message="Failed to queue task with puppeteer service"
                    )
                
                return CreateAmazonAffiliateLink(
                    taskId=task_id,
                    affiliateUrl="pending",
                    status="processing",
                    message="Affiliate link is being generated"
                )
                
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Error in CreateAmazonAffiliateLink: {str(e)}\n{tb}")
            return CreateAmazonAffiliateLink(
                taskId=None,
                affiliateUrl=None,
                status="error",
                message=str(e)
            )

class UpdateAffiliateLink(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        is_active = graphene.Boolean()
    
    affiliate_link = graphene.Field(AffiliateLinkType)
    
    @staticmethod
    def mutate(root, info, id, is_active=None):
        try:
            affiliate_link = AffiliateLinkModel.objects.get(pk=id)
            
            if is_active is not None:
                affiliate_link.is_active = is_active
                
            affiliate_link.save()
            
            return UpdateAffiliateLink(affiliate_link=affiliate_link)
        except AffiliateLinkModel.DoesNotExist:
            raise GraphQLError(f"Affiliate link with ID {id} not found")
        except Exception as e:
            raise GraphQLError(str(e))

class AddToCart(graphene.Mutation):
    class Arguments:
        session_id = graphene.String()
        cart_id = graphene.ID()
        item = CartItemInput(required=True)
    
    cart = graphene.Field(CartType)
    
    @staticmethod
    def mutate(root, info, item, session_id=None, cart_id=None):
        # Get or create cart
        cart = None
        user = info.context.user
        
        if cart_id:
            cart = Cart.objects.get(pk=cart_id)
        elif session_id:
            cart, created = Cart.objects.get_or_create(
                session_id=session_id,
                defaults={'user': user if user.is_authenticated else None}
            )
        elif user.is_authenticated:
            cart, created = Cart.objects.get_or_create(
                user=user,
                defaults={'session_id': ''}
            )
        else:
            # Generate new session ID if needed
            import uuid
            new_session_id = str(uuid.uuid4())
            cart = Cart.objects.create(session_id=new_session_id)
        
        # Get the offer
        offer = OfferModel.objects.get(pk=item.offer_id)
        
        # Check if item already in cart
        try:
            cart_item = CartItem.objects.get(cart=cart, offer=offer)
            cart_item.quantity += item.quantity
            cart_item.save()
        except CartItem.DoesNotExist:
            cart_item = CartItem.objects.create(
                cart=cart,
                offer=offer,
                quantity=item.quantity
            )
        
        return AddToCart(cart=cart)

class UpdateCartItem(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        quantity = graphene.Int(required=True)
    
    cart_item = graphene.Field(CartItemType)
    
    @staticmethod
    def mutate(root, info, id, quantity):
        cart_item = CartItem.objects.get(pk=id)
        
        if quantity <= 0:
            cart_item.delete()
            return None
        
        cart_item.quantity = quantity
        cart_item.save()
        
        return UpdateCartItem(cart_item=cart_item)

class RemoveFromCart(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    
    success = graphene.Boolean()
    
    @staticmethod
    def mutate(root, info, id):
        try:
            cart_item = CartItem.objects.get(pk=id)
            cart_item.delete()
            return RemoveFromCart(success=True)
        except CartItem.DoesNotExist:
            return RemoveFromCart(success=False)

class ClearCart(graphene.Mutation):
    class Arguments:
        cart_id = graphene.ID()
        session_id = graphene.String()
    
    success = graphene.Boolean()
    
    @staticmethod
    def mutate(root, info, cart_id=None, session_id=None):
        cart = None
        
        if cart_id:
            try:
                cart = Cart.objects.get(pk=cart_id)
            except Cart.DoesNotExist:
                return ClearCart(success=False)
        elif session_id:
            try:
                cart = Cart.objects.get(session_id=session_id)
            except Cart.DoesNotExist:
                return ClearCart(success=False)
        else:
            return ClearCart(success=False)
        
        CartItem.objects.filter(cart=cart).delete()
        return ClearCart(success=True)

class Mutation(AuthMutation, ProductMutation, AffiliateMutation, CartMutation, graphene.ObjectType):
    # Product mutations
    create_product = CreateProduct.Field()
    update_product = UpdateProduct.Field()
    create_product_from_amazon = CreateProductFromAmazon.Field()
    
    # Affiliate link mutations
    create_affiliate_link = CreateAffiliateLink.Field()
    create_amazon_affiliate_link = CreateAmazonAffiliateLink.Field()
    update_affiliate_link = UpdateAffiliateLink.Field()
    
    # Cart mutations
    add_to_cart = AddToCart.Field()
    update_cart_item = UpdateCartItem.Field()
    remove_from_cart = RemoveFromCart.Field()
    clear_cart = ClearCart.Field()

# Add a Dimensions type that matches the fragment
class Dimensions(graphene.ObjectType):
    length = graphene.Float()
    width = graphene.Float()
    height = graphene.Float()

# Create a pagination container for products
class ProductConnection(graphene.ObjectType):
    """Simple connection type for products"""
    total_count = graphene.Int()
    items = graphene.List(ProductType)
    
    # Add alias for camelCase if needed
    totalCount = graphene.Int()
    
    def resolve_totalCount(self, info):
        return self.total_count

# Add this new class to support Relay-style connections
class ProductEdge(graphene.ObjectType):
    node = graphene.Field(ProductType)
    cursor = graphene.String()

class RelayStyleProductConnection(graphene.ObjectType):
    edges = graphene.List(ProductEdge)
    pageInfo = graphene.Field('ecommerce_platform.schema.PageInfo')

class PageInfo(graphene.ObjectType):
    hasNextPage = graphene.Boolean()
    hasPreviousPage = graphene.Boolean()
    startCursor = graphene.String()
    endCursor = graphene.String()

class ProductSearchResult(graphene.ObjectType):
    """Enhanced wrapper type for product search results with detailed relationship classification"""
    id = graphene.ID()
    name = graphene.String()
    part_number = graphene.String()
    description = graphene.String()
    main_image = graphene.String()
    manufacturer = graphene.Field(ManufacturerType)
    affiliate_links = graphene.List(AffiliateLinkType)
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
    affiliateLinks = graphene.List(AffiliateLinkType)
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
        return self.affiliate_links

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
                    
                affiliate_link = AffiliateLinkModel.objects.filter(
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
                return ProductModel.objects.get(id=self.id)
            except ProductModel.DoesNotExist:
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
                affiliate_links = AffiliateLinkModel.objects.filter(
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
            return list(AffiliateLinkModel.objects.filter(product=self._source_product))
        
        return []

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

# Add this helper function near the top of your file
def ensure_product_has_amazon_affiliate_link(product):
    """
    Check if a product has an Amazon affiliate link, and create one if it doesn't.
    Returns the list of all affiliate links for the product.
    """
    # Check for existing Amazon affiliate link first
    amazon_link = AffiliateLinkModel.objects.filter(
        product=product, 
        platform='amazon'
    ).first()
    
    # Get all affiliate links for this product
    product_links = list(AffiliateLinkModel.objects.filter(product=product))
    
    # If we don't have an Amazon link already, create one if possible
    if not amazon_link and product.part_number:
        try:
            logger.info(f"Creating new Amazon affiliate link for product {product.id} with part number {product.part_number}")
            # Create a basic affiliate link that will be populated later
            affiliate_link = AffiliateLinkModel(
                product=product,
                platform='amazon',
                platform_id=product.part_number,
                original_url=f"https://www.amazon.com/dp/{product.part_number}",
                affiliate_url='',  # Will be populated by background task
                is_active=True
            )
            affiliate_link.save()
            
            # Queue background task to generate actual affiliate URL
            async_task('affiliates.tasks.generate_amazon_affiliate_url', 
                      affiliate_link.id, product.part_number)
            
            # Add the new link to our list
            product_links.append(affiliate_link)
        except Exception as e:
            logger.error(f"Failed to create affiliate link: {str(e)}")
    
    return product_links

@lru_cache(maxsize=1)
def get_significant_terms():
    """
    Analyze all products to find significant terms that indicate product categories.
    Uses caching to avoid repeating this expensive operation.
    """
    logger.info("Analyzing product database to extract significant terms")
    
    # Get all product names and descriptions
    all_products = ProductModel.objects.all()
    all_text = " ".join([
        (p.name + " " + (p.description or "")).lower() 
        for p in all_products
    ])
    
    # Tokenize and count terms
    words = re.findall(r'\b\w+\b', all_text)
    word_counts = Counter(words)
    
    # Remove common stop words
    stop_words = set(stopwords.words('english'))
    stop_words.update(['the', 'and', 'with', 'for', 'this', 'that', 'from'])
    
    # Find significant terms (frequent enough but not too common)
    significant_terms = {}
    total_products = all_products.count()
    
    for word, count in word_counts.items():
        # Skip stop words and short words
        if word in stop_words or len(word) < 3:
            continue
            
        # Calculate significance - terms that appear in 0.1% to 20% of products
        frequency = count / total_products
        if 0.001 <= frequency <= 0.2:
            significant_terms[word] = count
    
    logger.info(f"Extracted {len(significant_terms)} significant terms from product database")
    return significant_terms

# Add this new type for the response
class AffiliateTaskStatus(graphene.ObjectType):
    task_id = graphene.String()
    status = graphene.String()
    affiliate_url = graphene.String()
    error = graphene.String()
    
    # Add camelCase aliases for frontend compatibility
    taskId = graphene.String()
    affiliateUrl = graphene.String()
    
    def resolve_taskId(self, info):
        return self.task_id
    
    def resolve_affiliateUrl(self, info):
        return self.affiliate_url

def extract_search_terms(search_text):
    """Extract meaningful search terms from Amazon product names"""
    import re
    
    # Clean up the text
    text = search_text.lower()
    
    # Extract brand/manufacturer (usually first word)
    words = text.split()
    brand = words[0] if words else ""
    
    # Extract model numbers (alphanumeric patterns)
    models = re.findall(r'\b[a-z]*\d+[a-z0-9]*\b', text)
    
    # Extract key product terms
    key_terms = []
    for word in words:
        if len(word) > 2 and word not in ['the', 'and', 'with', 'for', 'gaming', 'pro']:
            key_terms.append(word)
    
    return {
        'brand': brand,
        'models': models,
        'key_terms': key_terms[:5],  # Top 5 terms
        'full_text': text
    }

def find_product_candidates(search_terms):
    """Find potential product matches using various strategies"""
    from django.db.models import Q
    
    candidates = []
    
    # Strategy A: Brand + Model matching
    if search_terms['brand'] and search_terms['models']:
        brand_query = Q(manufacturer__name__icontains=search_terms['brand'])
        
        for model in search_terms['models']:
            model_query = Q(name__icontains=model) | Q(part_number__icontains=model)
            brand_model_candidates = ProductModel.objects.filter(brand_query & model_query)
            candidates.extend(brand_model_candidates)
    
    # Strategy B: Key terms matching
    if search_terms['key_terms']:
        term_query = Q()
        for term in search_terms['key_terms']:
            term_query |= Q(name__icontains=term) | Q(description__icontains=term)
        
        term_candidates = ProductModel.objects.filter(term_query)
        candidates.extend(term_candidates)
    
    # Remove duplicates
    unique_candidates = []
    seen_ids = set()
    for candidate in candidates:
        if candidate.id not in seen_ids:
            unique_candidates.append(candidate)
            seen_ids.add(candidate.id)
    
    return unique_candidates[:10]  # Limit to top 10

def score_and_select_best_match(search_text, candidates):
    """Score candidates and return the best match"""
    if not candidates:
        return None
    
    best_score = 0
    best_product = None
    
    search_lower = search_text.lower()
    
    for product in candidates:
        score = 0
        
        # Exact name match gets highest score
        if search_lower == product.name.lower():
            return product
        
        # Partial name matching
        if search_lower in product.name.lower():
            score += 50
        
        # Part number similarity
        if search_lower in product.part_number.lower():
            score += 30
        
        # Manufacturer match
        if product.manufacturer and product.manufacturer.name.lower() in search_lower:
            score += 20
        
        # Word overlap
        search_words = set(search_lower.split())
        product_words = set(product.name.lower().split())
        overlap = len(search_words & product_words)
        score += overlap * 5
        
        debug_logger.info(f"📊 Candidate: {product.name} (score: {score})")
        
        if score > best_score:
            best_score = score
            best_product = product
    
    # Only return if we have a decent confidence score
    if best_score >= 25:  # Minimum threshold
        debug_logger.info(f"🎯 Best match: {best_product.name} (score: {best_score})")
        return best_product
    
    debug_logger.warning(f"⚠️ No confident match found (best score: {best_score})")
    return None

def handle_affiliate_link_for_asin(product, asin, url):
    """Handle affiliate link creation/retrieval for a product and ASIN"""
    try:
        # Try to find existing affiliate link
        affiliate_link = AffiliateLinkModel.objects.get(
            product=product,
            platform='amazon',
            platform_id=asin
        )
        debug_logger.info(f"🔗 Found existing affiliate link: {affiliate_link.id}")
        return affiliate_link
        
    except AffiliateLinkModel.DoesNotExist:
        # Create new affiliate link
        debug_logger.info(f"🔗 Creating new affiliate link for ASIN: {asin}")
        
        affiliate_link = AffiliateLinkModel(
            product=product,
            platform='amazon',
            platform_id=asin,
            original_url=url or f"https://www.amazon.com/dp/{asin}",
            affiliate_url='',  # Will be populated by background task
            is_active=True
        )
        affiliate_link.save()
        
        # Queue background task to generate actual affiliate URL
        task_result = async_task('affiliates.tasks.generate_amazon_affiliate_url', 
                      affiliate_link.id, asin)
        
        debug_logger.info(f"🚀 Queued affiliate task: {task_result}")
        return affiliate_link

# Helper functions for ASIN search
def ensure_affiliate_link_exists(asin):
    """Always ensure we have an affiliate link for this ASIN"""
    
    # Check if one exists
    existing_link = AffiliateLinkModel.objects.filter(
        platform='amazon',
        platform_id=asin
    ).first()
    
    if existing_link:
        debug_logger.info(f"✅ Affiliate link exists: {existing_link.id}")
        return existing_link
    
    # Create one if it doesn't exist
    debug_logger.info(f"🚀 Creating affiliate link for ASIN: {asin}")
    try:
        task_result = async_task('affiliates.tasks.generate_standalone_amazon_affiliate_url', asin)
        debug_logger.info(f"Task queued: {task_result}")
        
        # The task will create the affiliate link, but we need to return something now
        # Create a placeholder that will be populated by the task
        new_link = AffiliateLinkModel.objects.create(
            platform='amazon',
            platform_id=asin,
            original_url=f"https://amazon.com/dp/{asin}",
            affiliate_url='',  # Will be populated by task
            is_active=True
        )
        debug_logger.info(f"📝 Created placeholder affiliate link: {new_link.id}")
        return new_link
        
    except Exception as e:
        debug_logger.error(f"❌ Failed to create affiliate link: {str(e)}")
        return None

def get_amazon_product_by_asin(asin):
    """Find the Amazon product we created for this ASIN"""
    
    # Method 1: Look for affiliate link with this ASIN
    affiliate_link = AffiliateLinkModel.objects.filter(
        platform='amazon',
        platform_id=asin
    ).select_related('product').first()
    
    if affiliate_link and affiliate_link.product:
        debug_logger.info(f"📦 Found Amazon product via affiliate link: {affiliate_link.product.name}")
        return affiliate_link.product
    
    # Method 2: Look for product with ASIN as part number (fallback)
    try:
        product = ProductModel.objects.get(part_number=asin)
        debug_logger.info(f"📦 Found Amazon product via part number: {product.name}")
        return product
    except ProductModel.DoesNotExist:
        pass
    
    # Method 3: Look for product name containing ASIN
    products_with_asin = ProductModel.objects.filter(
        Q(name__icontains=asin) | Q(description__icontains=asin)
    ).first()
    
    if products_with_asin:
        debug_logger.info(f"📦 Found Amazon product via name/description: {products_with_asin.name}")
        return products_with_asin
    
    debug_logger.warning(f"❌ No Amazon product found for ASIN: {asin}")
    return None

def find_similar_products(amazon_product, limit):
    """Find products in our database that are similar to the Amazon product"""
    
    candidates = []
    seen_ids = {amazon_product.id}  # Don't include the Amazon product itself
    
    # Strategy 1: Try exact part number match first (keep original logic)
    debug_logger.info(f"🔍 Strategy 1: Trying exact part number match...")
    if amazon_product.part_number:
        exact_matches = ProductModel.objects.filter(
            part_number__iexact=amazon_product.part_number,
            offers__isnull=False  # Only products with offers
        ).distinct()
        
        for product in exact_matches:
            if product.id not in seen_ids and len(candidates) < limit:
                candidates.append(product)
                seen_ids.add(product.id)
                debug_logger.info(f"✅ Exact match: {product.part_number}")
    
    # Strategy 2: Fuzzy matching by key terms (keep original logic)
    debug_logger.info(f"🔍 Strategy 2: Fuzzy matching by key terms...")
    search_terms = extract_search_terms_from_name(amazon_product.name)
    debug_logger.info(f"🔍 Search terms: {search_terms[:3]}...")  # Log first 3
    
    if len(candidates) < limit:
        for term in search_terms[:5]:  # Try top 5 terms
            fuzzy_matches = ProductModel.objects.filter(
                Q(name__icontains=term) | Q(part_number__icontains=term),
                offers__isnull=False
            ).distinct()
            
            for product in fuzzy_matches:
                if product.id not in seen_ids and len(candidates) < limit:
                    candidates.append(product)
                    seen_ids.add(product.id)
                    debug_logger.info(f"🔍 Fuzzy candidate: {product.name} (term: {term})")
    
    # Strategy 3: ENHANCED PART NUMBER EXTRACTION (only if we need more candidates)
    debug_logger.info(f"🔍 Strategy 3: Part number extraction (if needed)...")
    if len(candidates) < limit:
        try:
            extracted_matches = find_products_by_extracted_part_numbers(amazon_product)
            
            for product in extracted_matches:
                if product.id not in seen_ids and len(candidates) < limit:
                    candidates.append(product)
                    seen_ids.add(product.id)
                    debug_logger.info(f"🎯 EXTRACTED PART MATCH: {product.part_number}")
        except Exception as e:
            debug_logger.error(f"❌ Part number extraction failed: {e}")
    
    # Strategy 4: Validate and score candidates (simplified)
    debug_logger.info(f"🔍 Strategy 4: Validating {len(candidates)} candidates...")
    lower_amazon_text = (amazon_product.name + " " + (amazon_product.description or "")).lower()
    
    # Simple validation: boost confidence for part numbers found in Amazon text
    for product in candidates:
        if product.part_number and product.part_number.lower() in lower_amazon_text:
            debug_logger.info(f"🎯 VALIDATION: {product.part_number} confirmed in Amazon text")
    
    debug_logger.info(f"🎯 Final results: {len(candidates)} products")
    return candidates[:limit]

def extract_search_terms_from_name(product_name):
    """Extract meaningful search terms from product name"""
    import re
    
    # Remove common filler words and extract meaningful terms
    name_lower = product_name.lower()
    
    # Extract alphanumeric terms (product codes, model numbers)
    terms = re.findall(r'\b[a-z0-9\-]+\b', name_lower)
    
    # Filter out very short or very common terms
    filtered_terms = []
    skip_words = {'the', 'and', 'or', 'with', 'for', 'plus', 'pro', 'max', 'new'}
    
    for term in terms:
        if len(term) >= 3 and term not in skip_words:
            filtered_terms.append(term)
    
    return filtered_terms

def extract_potential_part_numbers(amazon_text):
    """
    Extract potential part numbers from Amazon product text using common patterns
    """
    import re
    
    potential_parts = []
    text = amazon_text.upper()  # Convert to uppercase for consistency
    
    # Pattern 1: Common part number formats (letters + numbers with optional separators)
    # Examples: MSI-Z790CARBWIFI, RTX4080, B550-PLUS, etc.
    patterns = [
        r'\b[A-Z]{2,4}[-\s]?[A-Z0-9]{3,12}\b',  # MSI-Z790CARBWIFI, RTX-4080
        r'\b[A-Z0-9]{3,4}-[A-Z0-9]{3,12}\b',    # B550-TOMAHAWK, Z790-GAMING
        r'\b[A-Z]{1,3}\d{3,4}[A-Z]{0,4}\b',     # RTX4080, B550M, Z790
        r'\b\d{3,4}[A-Z]{1,4}\b',               # 4080TI, 550M
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # Clean up the match
            clean_match = match.strip().replace(' ', '-')
            if len(clean_match) >= 4 and clean_match not in potential_parts:
                potential_parts.append(clean_match)
    
    # Pattern 2: Look for text in parentheses (often contains part numbers)
    paren_content = re.findall(r'\(([^)]+)\)', text)
    for content in paren_content:
        # Check if parentheses content looks like a part number
        if re.match(r'^[A-Z0-9\-\s]{4,15}$', content.strip()):
            clean_content = content.strip().replace(' ', '-')
            if clean_content not in potential_parts:
                potential_parts.append(clean_content)
    
    debug_logger.info(f"📝 Extracted potential part numbers: {potential_parts}")
    return potential_parts

def find_products_by_extracted_part_numbers(amazon_product):
    """
    Try to find exact matches using part numbers extracted from Amazon text
    """
    amazon_text = amazon_product.name + " " + (amazon_product.description or "")
    potential_parts = extract_potential_part_numbers(amazon_text)
    
    exact_matches = []
    
    for part_candidate in potential_parts:
        # Try exact match
        matches = ProductModel.objects.filter(
            part_number__iexact=part_candidate,
            offers__isnull=False
        ).exclude(id=amazon_product.id)
        
        for match in matches:
            if match not in exact_matches:
                exact_matches.append(match)
                debug_logger.info(f"🎯 EXACT PART NUMBER MATCH: {match.part_number} matched extracted '{part_candidate}'")
        
        # Try partial matches (part number contains the candidate)
        partial_matches = ProductModel.objects.filter(
            part_number__icontains=part_candidate,
            offers__isnull=False
        ).exclude(id=amazon_product.id)
        
        for match in partial_matches:
            if match not in exact_matches:
                exact_matches.append(match)
                debug_logger.info(f"🎯 PARTIAL PART NUMBER MATCH: {match.part_number} contains extracted '{part_candidate}'")
    
    return exact_matches

schema = graphene.Schema(query=Query, mutation=Mutation)