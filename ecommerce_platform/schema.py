import graphene
import logging
import json
import re
import os  # Add this import
import datetime  # Add this import
import traceback  # Add this import
import uuid  # Add this import
from urllib.parse import urlparse  # Add this import
from typing import List, Optional
from dataclasses import dataclass
from functools import lru_cache
from collections import Counter
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from graphql import GraphQLError
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
import redis
from graphene import relay
from django_q.tasks import async_task  # Add this import
from django.conf import settings  # Add this import
from django.utils.text import slugify  # Add this import

# Import models
from products.models import (
    Product as ProductModel, 
    Category as CategoryModel, 
    Manufacturer as ManufacturerModel
    # Remove Offer as OfferModel from here
)
from offers.models import Offer as OfferModel  # Add this line
from affiliates.models import AffiliateLink as AffiliateLinkModel  # Add this line
from affiliates.models import AffiliateLink as AffiliateLinkModel, ProductAssociation  # Add this line
from store.models import Cart as CartModel, CartItem as CartItemModel  # Fix import path

# Import GraphQL types
from ecommerce_platform.graphql.types.product import CategoryType, ManufacturerType, ProductType  # Add ProductType here
from ecommerce_platform.graphql.types.offer import OfferType
from ecommerce_platform.graphql.types.affiliate import AffiliateLinkType, ProductAssociationType
from ecommerce_platform.graphql.types.cart import CartType, CartItemType
from ecommerce_platform.graphql.types.user import UserType
from ecommerce_platform.graphql.mutations.auth import AuthMutation
from ecommerce_platform.graphql.mutations.product import ProductMutation
from ecommerce_platform.graphql.mutations.affiliate import AffiliateMutation
from ecommerce_platform.graphql.mutations.cart import CartMutation

# Import affiliate functions
from affiliates.tasks import generate_standalone_amazon_affiliate_url, generate_affiliate_url_from_search

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

# Add the OfferTypeEnum that Chrome extension expects
class OfferTypeEnum(graphene.Enum):
    SUPPLIER = 'supplier'
    AFFILIATE = 'affiliate'

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
    
    # Add Chrome Extension compatible offer queries (camelCase)
    offersByProduct = graphene.List(
        'ecommerce_platform.graphql.types.offer.OfferType',
        productId=graphene.ID(required=True),
        offerType=OfferTypeEnum(),
        description="Chrome extension compatible offers query (camelCase)"
    )
    
    # Add Chrome Extension compatible pricing intelligence query
    priceComparison = graphene.List(
        'ecommerce_platform.graphql.types.offer.OfferType',
        productId=graphene.ID(required=True),
        includeAffiliate=graphene.Boolean(default_value=True),
        includeSupplier=graphene.Boolean(default_value=True),
        description="Chrome extension compatible price comparison query (camelCase)"
    )
    
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
        wait_for_affiliate=graphene.Boolean(default_value=False),
        description="Unified search endpoint for Chrome extension"
    )
    
    # Add camelCase alias for Chrome extension compatibility
    unifiedProductSearch = graphene.List(
        'ecommerce_platform.schema.ProductSearchResult',
        asin=graphene.String(),
        partNumber=graphene.String(),
        name=graphene.String(),
        url=graphene.String(),
        waitForAffiliate=graphene.Boolean(default_value=False),
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
        search_term=graphene.String(required=True),
        limit=graphene.Int(default_value=20),
        description="Enhanced consumer product search with Amazon API integration"
    )
    
    # Product association queries for search optimization
    product_associations = graphene.List(
        ProductAssociationType,
        search_term=graphene.String(),
        source_product_id=graphene.ID(),
        target_product_id=graphene.ID(),
        association_type=graphene.String(),
        limit=graphene.Int(default_value=10),
        description="Get product associations for search optimization"
    )
    
    # Check for existing alternatives before Amazon search
    existing_alternatives = graphene.List(
        ProductAssociationType,
        search_term=graphene.String(required=True),
        description="Check for existing product alternatives based on search term"
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
    
    def resolve_offersByProduct(self, info, productId, offerType=None):
        """Chrome extension compatible offers resolver (camelCase)"""
        queryset = OfferModel.objects.filter(
            product_id=productId,
            is_active=True,
            is_in_stock=True
        )
        
        # Filter by offer type if specified (convert enum to string)
        if offerType:
            offer_type_value = offerType.value if hasattr(offerType, 'value') else str(offerType)
            queryset = queryset.filter(offer_type=offer_type_value)
        
        return queryset.select_related('product', 'vendor').order_by('selling_price')
    
    def resolve_priceComparison(self, info, productId, includeAffiliate=True, includeSupplier=True):
        """Chrome extension compatible price comparison resolver (camelCase)"""
        queryset = OfferModel.objects.filter(
            product_id=productId,
            is_active=True,
            is_in_stock=True
        )
        
        # Filter by offer types based on preferences
        offer_types = []
        if includeSupplier:
            offer_types.append('supplier')
        if includeAffiliate:
            offer_types.append('affiliate')
        
        if offer_types:
            queryset = queryset.filter(offer_type__in=offer_types)
        
        return queryset.select_related('product', 'vendor').order_by('selling_price')
    
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
        wait_for_affiliate=graphene.Boolean(default_value=False),
        description="Unified search endpoint for Chrome extension"
    )
    
    # Add camelCase alias for Chrome extension compatibility
    unifiedProductSearch = graphene.List(
        'ecommerce_platform.schema.ProductSearchResult',
        asin=graphene.String(),
        partNumber=graphene.String(),
        name=graphene.String(),
        url=graphene.String(),
        waitForAffiliate=graphene.Boolean(default_value=False),
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
        search_term=graphene.String(required=True),
        limit=graphene.Int(default_value=20),
        description="Enhanced consumer product search with Amazon API integration"
    )
    
    # Product association queries for search optimization
    product_associations = graphene.List(
        ProductAssociationType,
        search_term=graphene.String(),
        source_product_id=graphene.ID(),
        target_product_id=graphene.ID(),
        association_type=graphene.String(),
        limit=graphene.Int(default_value=10),
        description="Get product associations for search optimization"
    )
    
    # Check for existing alternatives before Amazon search
    existing_alternatives = graphene.List(
        ProductAssociationType,
        search_term=graphene.String(required=True),
        description="Check for existing product alternatives based on search term"
    )
    
    def resolve_offers_by_product(self, info, product_id):
        return OfferModel.objects.filter(product_id=product_id)
    
    def resolve_offersByProduct(self, info, productId, offerType=None):
        """Chrome extension compatible offers resolver (camelCase)"""
        queryset = OfferModel.objects.filter(
            product_id=productId,
            is_active=True,
            is_in_stock=True
        )
        
        # Filter by offer type if specified (convert enum to string)
        if offerType:
            offer_type_value = offerType.value if hasattr(offerType, 'value') else str(offerType)
            queryset = queryset.filter(offer_type=offer_type_value)
        
        return queryset.select_related('product', 'vendor').order_by('selling_price')
    
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
        UPDATED: Chrome extension search with FIXED keyboard alternative logic
        
        Now uses the corrected _search_internal_inventory_static method that properly 
        detects product types and returns relevant alternatives (Dell keyboards, cross-brand keyboards, etc.)
        """
        debug_logger.info(f"=== PRODUCTS SEARCH (Chrome Extension) ===")
        debug_logger.info(f"Request: term='{term}', asin='{asin}', max_price={max_price}")
        
        # If no term provided, return empty result (backward compatibility)
        if not term:
            debug_logger.warning(f"⚠️ No search term provided, returning empty results")
            return ProductModel.objects.none()

        # PRIORITY 1: Use the FIXED internal inventory search that properly handles alternatives
        debug_logger.info(f"🔍 Using FIXED internal inventory search for alternatives...")
        try:
            # Use the corrected search method that properly detects keyboards and finds alternatives
            search_results = Query._search_internal_inventory_static(name=term)
            
            if search_results:
                debug_logger.info(f"✅ Found {len(search_results)} results via fixed search logic")
                
                # Convert ProductSearchResult objects to actual Product models for compatibility
                final_products = []
                for result in search_results:
                    if hasattr(result, '_source_product') and result._source_product:
                        final_products.append(result._source_product)
                    else:
                        # For Amazon products or when no source product, try to find by ID
                        try:
                            if result.id and str(result.id).isdigit():
                                product = ProductModel.objects.get(id=result.id)
                                final_products.append(product)
                        except (ProductModel.DoesNotExist, ValueError):
                            debug_logger.warning(f"Could not find product for result: {result.name}")
                
                debug_logger.info(f"📊 Converted to {len(final_products)} Product objects")
                
                # Apply price filter if provided
                if max_price is not None and final_products:
                    from decimal import Decimal
                    try:
                        max_price_decimal = Decimal(str(max_price))
                        filtered_products = []
                        for product in final_products:
                            # Always include demo products regardless of price
                            if hasattr(product, 'is_demo') and product.is_demo:
                                filtered_products.append(product)
                                continue
                                
                            # For non-demo products, check if they have offers within price range
                            offers = OfferModel.objects.filter(product=product, selling_price__lte=max_price_decimal)
                            if offers.exists():
                                filtered_products.append(product)
                        final_products = filtered_products
                        debug_logger.info(f"💰 Applied price filter: {len(final_products)} products")
                    except (ValueError, TypeError):
                        debug_logger.warning(f"⚠️ Invalid price filter: {max_price}")
                
                # Return queryset for compatibility with Chrome extension format
                if final_products:
                    product_ids = [p.id for p in final_products]
                    from django.db.models import Case, When, IntegerField
                    order_cases = [When(id=product_id, then=i) for i, product_id in enumerate(product_ids)]
                    result = ProductModel.objects.filter(id__in=product_ids).annotate(
                        custom_order=Case(*order_cases, output_field=IntegerField())
                    ).order_by('custom_order')
                    
                    debug_logger.info(f"🎯 RESULT: Returning {result.count()} products via FIXED search logic")
                    return result
                else:
                    debug_logger.info(f"🎯 RESULT: No products after filtering")
                    return ProductModel.objects.none()
        
        except Exception as e:
            debug_logger.error(f"❌ Fixed search logic failed: {str(e)}")
            import traceback
            traceback.print_exc()

        # FALLBACK: Original simple search (no alternatives, exact matches only)
        debug_logger.info(f"🔄 Using fallback search logic (exact matches only)")
        
        qs = ProductModel.objects.filter(status='active').order_by('name')
        
        # Search by product name/description/part number
        if term:
            qs = qs.filter(
                Q(name__icontains=term) | 
                Q(description__icontains=term) |
                Q(part_number__icontains=term)
            )
        
        # Apply price filter
        if max_price is not None:
            from decimal import Decimal
            try:
                max_price_decimal = Decimal(str(max_price))
                qs = qs.filter(offers__selling_price__lte=max_price_decimal).distinct()
            except (ValueError, TypeError):
                pass
        
        debug_logger.info(f"🎯 FALLBACK RESULT: Returning {qs.count()} products")
        return qs
    
    def resolve_unifiedProductSearch(self, info, asin=None, partNumber=None, name=None, url=None, waitForAffiliate=False):
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
                debug_logger.info(f"🔄 waitForAffiliate: {waitForAffiliate}")
                
                # CORE BUSINESS LOGIC: Always ensure affiliate link exists for ASIN
                affiliate_link = ensure_affiliate_link_exists(asin)
                debug_logger.info(f"🔗 Affiliate link: {'✅ Found' if affiliate_link and affiliate_link.affiliate_url else '⏳ Pending/Created'}")
                
                # NEW: Server-side waiting logic when waitForAffiliate=True
                if waitForAffiliate and affiliate_link and not affiliate_link.affiliate_url:
                    debug_logger.info(f"⏳ Waiting for affiliate link completion...")
                    # Reduce timeout to 5 seconds to prevent Heroku request timeout
                    try:
                        affiliate_link, completed = wait_for_affiliate_completion(asin, timeout_seconds=5)
                        if completed:
                            debug_logger.info(f"✅ Affiliate link completed during wait")
                        else:
                            debug_logger.warning(f"⏰ Affiliate link generation timed out after 5 seconds")
                    except Exception as e:
                        debug_logger.error(f"❌ Error waiting for affiliate completion: {e}")
                        # Continue with the existing affiliate_link even if waiting failed
                
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
                        affiliate_links=[affiliate_link] if affiliate_link else [],
                        needs_affiliate_generation=(affiliate_link and not affiliate_link.affiliate_url),
                        is_placeholder=getattr(amazon_product, 'is_placeholder', False),
                        task_id=None
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
                        affiliate_links=[affiliate_link] if affiliate_link else [],
                        needs_affiliate_generation=True,
                        is_placeholder=True,
                        task_id=None
                    )
                    results.append(result)
                    debug_logger.info(f"📝 Created placeholder Amazon product for ASIN: {asin}")
                
                # ENHANCED ALTERNATIVES DISCOVERY - Find ALL relevant supplier products
                debug_logger.info(f"🔍 ASIN SEARCH: Looking for supplier alternatives using multiple strategies")
                
                # STRATEGY 1: Context-aware search (using full Amazon product name)
                try:
                    if name:
                        debug_logger.info(f"🧠 STRATEGY 1: Context-aware search using Amazon product name")
                        debug_logger.info(f"🔍 Amazon product: {name[:100]}...")
                        
                        context_alternatives = Query._search_internal_inventory_context_aware_static(
                            amazon_product_name=name
                        )
                        
                        debug_logger.info(f"🔍 Context-aware found {len(context_alternatives)} alternatives")
                        
                        # Process context-aware alternatives
                        for item in context_alternatives:
                            debug_logger.info(f"🔍 Context item: {item.name[:50]}... (ID: {getattr(item, 'id', 'unknown')})")
                            
                            # Check if this is an Amazon product
                            item_is_amazon = getattr(item, 'is_amazon_product', False)
                            if not item_is_amazon:
                                # Mark as alternative and add to results
                                item.is_alternative = True
                                item.relationship_type = "equivalent"
                                item.relationship_category = "context_aware_alternative"
                                results.append(item)
                                debug_logger.info(f"✅ ADDED context alternative: {item.name} (ID: {getattr(item, 'id', 'unknown')})")
                            else:
                                debug_logger.info(f"⚠️ SKIPPED Amazon product: {item.name}")
                        
                except Exception as e:
                    debug_logger.error(f"❌ Context-aware search failed: {e}", exc_info=True)
                
                # STRATEGY 2: Direct keyword search (fallback with specific terms)
                try:
                    debug_logger.info(f"🧠 STRATEGY 2: Direct keyword search for keyboard/mouse products")
                    
                    # Extract key terms from the Amazon product name
                    name_lower = name.lower() if name else ""
                    
                    # Build search terms based on product type
                    direct_search_terms = []
                    if 'keyboard' in name_lower and 'mouse' in name_lower:
                        direct_search_terms = ['keyboard mouse', 'keyboard and mouse', 'wireless keyboard mouse']
                    elif 'keyboard' in name_lower:
                        direct_search_terms = ['keyboard', 'wireless keyboard']
                    elif 'mouse' in name_lower:
                        direct_search_terms = ['mouse', 'wireless mouse']
                    
                    for search_term in direct_search_terms:
                        debug_logger.info(f"🔍 Direct search for: '{search_term}'")
                        
                        direct_alternatives = Query._search_internal_inventory_static(
                            part_number=None, 
                            name=search_term
                        )
                        
                        debug_logger.info(f"🔍 Direct search found {len(direct_alternatives)} results for '{search_term}'")
                        
                        # Add unique alternatives (avoid duplicates)
                        existing_ids = {getattr(r, 'id', None) for r in results}
                        
                        for item in direct_alternatives:
                            item_id = getattr(item, 'id', None)
                            if item_id and item_id not in existing_ids:
                                item_is_amazon = getattr(item, 'is_amazon_product', False)
                                if not item_is_amazon:
                                    item.is_alternative = True
                                    item.relationship_type = "equivalent"
                                    item.relationship_category = f"direct_search_{search_term.replace(' ', '_')}"
                                    results.append(item)
                                    existing_ids.add(item_id)
                                    debug_logger.info(f"✅ ADDED direct alternative: {item.name} (ID: {item_id})")
                
                except Exception as e:
                    debug_logger.error(f"❌ Direct keyword search failed: {e}", exc_info=True)
                
                # STRATEGY 3: Context-aware high-value product discovery 
                try:
                    debug_logger.info(f"🧠 STRATEGY 3: Context-aware high-value product discovery")
                    
                    # Extract context from Amazon product name to guide our search
                    context = Query._extract_product_context_static(name)
                    detected_category = context.get('category')
                    debug_logger.info(f"🔍 Detected product category: '{detected_category}' from name: '{name[:50]}...'")
                    
                    # Build context-aware search filters
                    category_filters = Query._build_category_specific_filters_static(detected_category)
                    
                    if category_filters:
                        debug_logger.info(f"🎯 Using category-specific filters for '{detected_category}'")
                        
                        # Get products with actual monetization opportunities
                        from django.db.models import Q, Exists, OuterRef
                        
                        high_value_products = ProductModel.objects.filter(
                            category_filters,  # ← SMART CONTEXT-AWARE FILTERS
                            Q(Exists(OfferModel.objects.filter(product=OuterRef('pk'))) | 
                              Exists(AffiliateLinkModel.objects.filter(product=OuterRef('pk'))))
                        ).select_related('manufacturer').prefetch_related('offers', 'affiliate_links')[:5]
                        
                        debug_logger.info(f"🔍 Context-aware search found {high_value_products.count()} {detected_category} accessories with offers/links")
                        
                        # Add unique context-aware alternatives
                        existing_ids = {getattr(r, 'id', None) for r in results}
                        
                        for product in high_value_products:
                            if product.id not in existing_ids:
                                # Check if this is an Amazon product (REFINED LOGIC)
                                is_amazon_product = False
                                if hasattr(product, 'manufacturer') and product.manufacturer:
                                    manufacturer_name = product.manufacturer.name.lower()
                                    # CRITICAL FIX: Only consider "Amazon" as Amazon product, not "Amazon Marketplace"
                                    # Amazon Marketplace products are actually supplier/third-party products sold through Amazon
                                    if manufacturer_name == 'amazon' or manufacturer_name.startswith('amazon,'):
                                        is_amazon_product = True
                                    # Amazon Marketplace = third-party sellers on Amazon = should be treated as suppliers
                                    elif 'amazon marketplace' in manufacturer_name:
                                        is_amazon_product = False  # Explicitly mark as NOT Amazon product
                                
                                if not is_amazon_product:
                                    # Convert to ProductSearchResult with proper relationship classification
                                    relationship_category = f"{detected_category}_accessory" if detected_category else "high_value_alternative"
                                    
                                    result = ProductSearchResult(
                                        id=product.id,
                                        name=product.name,
                                        part_number=product.part_number,
                                        description=product.description,
                                        main_image=product.main_image,
                                        manufacturer=product.manufacturer,
                                        is_amazon_product=False,
                                        is_alternative=True,
                                        match_type="context_aware_accessory",
                                        match_confidence=0.75,  # Slightly lower since these are accessories, not equivalents
                                        relationship_type="accessory",  # ← PROPER RELATIONSHIP TYPE
                                        relationship_category=relationship_category,  # ← CONTEXT-AWARE CATEGORY
                                        margin_opportunity="high",
                                        revenue_type="cross_sell_opportunity",  # ← MORE ACCURATE REVENUE TYPE
                                        offers=list(OfferModel.objects.filter(product=product).select_related('vendor')),
                                        affiliate_links=list(AffiliateLinkModel.objects.filter(product=product))
                                    )
                                    result._source_product = product
                                    results.append(result)
                                    existing_ids.add(product.id)
                                    debug_logger.info(f"✅ ADDED {detected_category} accessory: {product.name} (ID: {product.id})")
                    else:
                        debug_logger.info(f"⚠️ Category '{detected_category}' doesn't warrant accessory suggestions, skipping high-value discovery")
                
                except Exception as e:
                    debug_logger.error(f"❌ Context-aware high-value product discovery failed: {e}", exc_info=True)
                
                # COMPREHENSIVE LOGGING
                alternatives_count = len([r for r in results if getattr(r, 'is_alternative', False)])
                debug_logger.info(f"📊 FINAL ALTERNATIVES SUMMARY:")
                debug_logger.info(f"   Total results: {len(results)}")
                debug_logger.info(f"   Alternatives found: {alternatives_count}")
                debug_logger.info(f"   Primary Amazon product: {'✅' if any(not getattr(r, 'is_alternative', True) for r in results) else '❌'}")
                
                for i, result in enumerate(results):
                    result_type = "ALTERNATIVE" if getattr(result, 'is_alternative', False) else "PRIMARY"
                    result_id = getattr(result, 'id', 'unknown')
                    result_name = getattr(result, 'name', 'unknown')[:50]
                    debug_logger.info(f"   {i+1}. {result_type}: {result_name}... (ID: {result_id})")
                
                debug_logger.info(f"🎯 ASIN SEARCH COMPLETE: {len(results)} total results")
                return results
            
            # PRIORITY 2: Part Number Search (CDW, Staples, Microsoft, etc.)
            elif partNumber:
                debug_logger.info(f"🎯 Multi-Site Part Number Search: {partNumber}")
                
                # SMART FIX: Check if partNumber is actually an Amazon ASIN
                # ASIN format: 10 characters, alphanumeric, starts with B
                import re
                if re.match(r'^B[A-Z0-9]{9}$', partNumber):
                    debug_logger.info(f"🧠 DETECTED: partNumber '{partNumber}' is actually an ASIN! Redirecting to ASIN flow...")
                    return self.resolve_unifiedProductSearch(info, asin=partNumber, name=name, url=url, waitForAffiliate=waitForAffiliate)
                
                return Query._handle_non_amazon_product_search_static(partNumber=partNumber, name=name)
            
            # PRIORITY 3: Name Search (Universal Multi-Site)
            elif name:
                debug_logger.info(f"🎯 Universal Name Search: {name}")
                return Query._handle_non_amazon_product_search_static(name=name, partNumber=partNumber)
            
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
                    return self.resolve_unifiedProductSearch(info, asin=extracted_asin, waitForAffiliate=waitForAffiliate)
                
                debug_logger.info(f"⚠️  Could not extract product ID from URL: {url}")
                return []
            
            else:
                debug_logger.info("❌ No search parameters provided")
                return []
                
        except Exception as e:
            debug_logger.error(f"❌ Unified search error: {e}", exc_info=True)
            return []
    
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
        internal_results = Query._search_internal_inventory_static(partNumber, name)
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
            amazon_results = Query._dynamic_amazon_search_static(name or partNumber)
            results.extend(amazon_results)
        
        # STEP 3: Find Relevant Accessories (Cross-sell Opportunities)
        # Temporarily disable to prevent memory issues
        accessory_results = []  # Query._find_relevant_accessories_for_product_static(name or partNumber)
        results.extend(accessory_results)
        
        # STEP 4: Create Product Record for Future (Background task)
        Query._create_product_record_for_future_static(partNumber, name)
        
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
            # CRITICAL FIX: Prioritize products with offers and affiliate links
            exact_matches = ProductModel.objects.filter(
                part_number__iexact=part_number
            ).select_related('manufacturer').prefetch_related('offers', 'affiliate_links').extra(
                select={
                    'has_offers': 'CASE WHEN EXISTS(SELECT 1 FROM offers_offer WHERE offers_offer.product_id = products_product.id) THEN 1 ELSE 0 END',
                    'has_affiliate_links': 'CASE WHEN EXISTS(SELECT 1 FROM affiliates_affiliatelink WHERE affiliates_affiliatelink.product_id = products_product.id) THEN 1 ELSE 0 END'
                }
            ).order_by('-has_offers', '-has_affiliate_links', 'name')[:3]
            
            for product in exact_matches:
                # Track the first match for alternative searches
                if not primary_product_for_alternatives:
                    primary_product_for_alternatives = product
                
                # Determine if this is an Amazon product or supplier product
                is_amazon_product = False
                
                # IMPROVED: More intelligent Amazon product detection
                # 1. Check if manufacturer is explicitly Amazon/Amazon Marketplace
                if hasattr(product, 'manufacturer') and product.manufacturer:
                    manufacturer_name = product.manufacturer.name.lower()
                    if 'amazon' in manufacturer_name and ('marketplace' in manufacturer_name or manufacturer_name == 'amazon'):
                        is_amazon_product = True
                
                # 2. Check if product source indicates Amazon origin
                if hasattr(product, 'source') and product.source and 'amazon' in product.source.lower():
                    is_amazon_product = True
                
                # 3. Check if product is explicitly marked as placeholder
                if hasattr(product, 'is_placeholder') and product.is_placeholder:
                    is_amazon_product = True
                    
                # NOTE: We don't use main_image URL as indicator since supplier products 
                # often use Amazon images but are not Amazon products
                
                # Get ALL affiliate links (not just Amazon)
                all_affiliate_links = list(AffiliateLinkModel.objects.filter(
                    product=product
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
                    offers=list(OfferModel.objects.filter(product=product).select_related('vendor')),
                    affiliate_links=all_affiliate_links
                )
                result._source_product = product
                results.append(result)
                
            debug_logger.info(f"✅ Found {len(exact_matches)} exact part number matches")
        
        # PRIORITY 2: Intelligent brand/model-aware search (ALTERNATIVE products)
        # SMART FIX: Use the found product's name if no search name was provided
        search_name_for_alternatives = name
        if not search_name_for_alternatives and primary_product_for_alternatives:
            search_name_for_alternatives = primary_product_for_alternatives.name
            debug_logger.info(f"🧠 SMART FIX: Using found product name for alternatives: '{search_name_for_alternatives[:50]}...'")
        
        if search_name_for_alternatives and len(results) < 8:
            debug_logger.info(f"🧠 PRIORITY 2: Intelligent brand/model matching...")
            
            # Extract brand and product type from the search name
            name_lower = search_name_for_alternatives.lower()
            search_brand = None
            product_type = None
            
            # Brand detection
            if 'dell' in name_lower:
                search_brand = 'dell'
            elif 'apple' in name_lower or 'macbook' in name_lower:
                search_brand = 'apple'
            elif 'hp' in name_lower:
                search_brand = 'hp'
            elif 'lenovo' in name_lower or 'thinkpad' in name_lower:
                search_brand = 'lenovo'
            elif 'microsoft' in name_lower or 'surface' in name_lower:
                search_brand = 'microsoft'
            
            # Product type detection
            if any(laptop_term in name_lower for laptop_term in ['laptop', 'notebook', 'macbook', 'surface', 'thinkpad', 'latitude', 'xps']):
                product_type = 'laptop'
            elif any(monitor_term in name_lower for monitor_term in ['monitor', 'display', 'screen']):
                product_type = 'monitor'
            elif any(desktop_term in name_lower for desktop_term in ['desktop', 'pc', 'computer']):
                product_type = 'desktop'
            elif any(keyboard_term in name_lower for keyboard_term in ['keyboard', 'kb', 'typing']):
                product_type = 'keyboard'
            elif any(mouse_term in name_lower for mouse_term in ['mouse', 'mice', 'trackpad', 'pointing']):
                product_type = 'mouse'
            elif any(accessory_term in name_lower for accessory_term in ['cable', 'cord', 'adapter', 'charger', 'power', 'hub', 'dock', 'mount', 'stand']):
                product_type = 'accessory'
            
            debug_logger.info(f"🧠 Detected: brand='{search_brand}', type='{product_type}'")
            
            # STEP 1: Same-brand alternatives (HIGHEST PRIORITY)
            if search_brand and len(results) < 5:
                debug_logger.info(f"🎯 Looking for {search_brand} alternatives...")
                
                # IMPORTANT: Only look for same-brand alternatives if we have a clear product type
                # This prevents keyboards from getting laptop alternatives
                if not product_type:
                    debug_logger.info(f"⚠️ No clear product type detected, skipping same-brand alternatives to avoid irrelevant matches")
                else:
                    debug_logger.info(f"✅ Product type '{product_type}' detected, searching for {search_brand} {product_type} alternatives")
                
                    # CRITICAL FIX: Prioritize products with offers and affiliate links
                    same_brand_query = ProductModel.objects.filter(
                        manufacturer__name__icontains=search_brand,
                        status='active'
                    ).select_related('manufacturer').prefetch_related('offers', 'affiliate_links')
                    
                    # IMPORTANT: Order by monetization opportunities
                    same_brand_query = same_brand_query.extra(
                        select={
                            'has_offers': 'CASE WHEN EXISTS(SELECT 1 FROM offers_offer WHERE offers_offer.product_id = products_product.id) THEN 1 ELSE 0 END',
                            'has_affiliate_links': 'CASE WHEN EXISTS(SELECT 1 FROM affiliates_affiliatelink WHERE affiliates_affiliatelink.product_id = products_product.id) THEN 1 ELSE 0 END'
                        }
                    ).order_by('-has_offers', '-has_affiliate_links', 'name')
                
                    # Add product type filter if detected
                    if product_type == 'laptop':
                        same_brand_query = same_brand_query.filter(
                            Q(name__icontains='laptop') | Q(name__icontains='notebook') | 
                            Q(name__icontains='macbook') | Q(name__icontains='surface') |
                            Q(name__icontains='thinkpad') | Q(name__icontains='latitude') | Q(name__icontains='xps')
                        )
                    elif product_type == 'keyboard':
                        same_brand_query = same_brand_query.filter(
                            Q(name__icontains='keyboard') | Q(name__icontains='kb') | Q(name__icontains='typing')
                        )
                    elif product_type == 'mouse':
                        same_brand_query = same_brand_query.filter(
                            Q(name__icontains='mouse') | Q(name__icontains='mice') | Q(name__icontains='trackpad') | Q(name__icontains='pointing')
                        )
                    elif product_type == 'monitor':
                        same_brand_query = same_brand_query.filter(
                            Q(name__icontains='monitor') | Q(name__icontains='display') | Q(name__icontains='screen')
                        )
                    elif product_type == 'accessory':
                        same_brand_query = same_brand_query.filter(
                            Q(name__icontains='cable') | Q(name__icontains='cord') | Q(name__icontains='adapter') | 
                            Q(name__icontains='charger') | Q(name__icontains='power') | Q(name__icontains='hub') |
                            Q(name__icontains='dock') | Q(name__icontains='mount') | Q(name__icontains='stand')
                        )
                
                    # Skip products we already have
                    if results:
                        existing_ids = [r.id for r in results]
                        same_brand_query = same_brand_query.exclude(id__in=existing_ids)
                
                    same_brand_products = same_brand_query[:3]  # Limit to 3 same-brand alternatives
                
                    for product in same_brand_products:
                        # Check if this is an Amazon product using improved logic
                        is_amazon_product = False
                        
                        # 1. Check if manufacturer is explicitly Amazon/Amazon Marketplace
                        if hasattr(product, 'manufacturer') and product.manufacturer:
                            manufacturer_name = product.manufacturer.name.lower()
                            if 'amazon' in manufacturer_name and ('marketplace' in manufacturer_name or manufacturer_name == 'amazon'):
                                is_amazon_product = True
                        
                        # 2. Check if product source indicates Amazon origin
                        if hasattr(product, 'source') and product.source and 'amazon' in product.source.lower():
                            is_amazon_product = True
                        
                        # 3. Check if product is explicitly marked as placeholder
                        if hasattr(product, 'is_placeholder') and product.is_placeholder:
                            is_amazon_product = True
                    
                        # Get ALL affiliate links (not just Amazon)
                        all_affiliate_links = list(AffiliateLinkModel.objects.filter(
                            product=product
                        ))
                    
                        # Determine relationship category
                        relationship_category = "same_brand_alternative"
                        if hasattr(product, 'is_demo') and product.is_demo:
                            relationship_category = "same_brand_demo_alternative"
                        elif is_amazon_product:
                            relationship_category = "same_brand_amazon_alternative"
                    
                        result = ProductSearchResult(
                            id=product.id,
                            name=product.name,
                            part_number=product.part_number,
                            description=product.description,
                            main_image=product.main_image,
                            manufacturer=product.manufacturer,
                            is_amazon_product=is_amazon_product,
                            is_alternative=True,
                            match_type="same_brand_alternative",
                            match_confidence=0.85,  # High confidence for same brand
                            relationship_type="equivalent",
                            relationship_category=relationship_category,
                            margin_opportunity="high" if not is_amazon_product else "affiliate_only",
                            revenue_type="product_sale" if not is_amazon_product else "affiliate_commission",
                            offers=list(OfferModel.objects.filter(product=product).select_related('vendor')),
                            affiliate_links=all_affiliate_links
                        )
                        result._source_product = product
                        results.append(result)
                
                    debug_logger.info(f"🎯 Found {len(same_brand_products)} {search_brand} alternatives")
            
            # STEP 2: Cross-brand alternatives (LOWER PRIORITY)
            if product_type and len(results) < 6:
                debug_logger.info(f"🔍 Looking for cross-brand {product_type} alternatives...")
                
                # IMPORTANT: Only look for cross-brand alternatives if we have a clear product type
                # and it makes sense to have alternatives (laptops, monitors, keyboards, mice)
                alternative_worthy_types = ['laptop', 'monitor', 'keyboard', 'mouse', 'desktop']
                if product_type not in alternative_worthy_types:
                    debug_logger.info(f"⚠️ Product type '{product_type}' doesn't warrant cross-brand alternatives")
                else:
                    debug_logger.info(f"✅ Searching for cross-brand {product_type} alternatives")
                
                    # CRITICAL FIX: Prioritize products with offers and affiliate links
                    cross_brand_query = ProductModel.objects.filter(
                        status='active'
                    ).select_related('manufacturer').prefetch_related('offers', 'affiliate_links')
                    
                    # IMPORTANT: Order by monetization opportunities
                    cross_brand_query = cross_brand_query.extra(
                        select={
                            'has_offers': 'CASE WHEN EXISTS(SELECT 1 FROM offers_offer WHERE offers_offer.product_id = products_product.id) THEN 1 ELSE 0 END',
                            'has_affiliate_links': 'CASE WHEN EXISTS(SELECT 1 FROM affiliates_affiliatelink WHERE affiliates_affiliatelink.product_id = products_product.id) THEN 1 ELSE 0 END'
                        }
                    ).order_by('-has_offers', '-has_affiliate_links', 'name')
                
                    # Filter by product type
                    if product_type == 'laptop':
                        cross_brand_query = cross_brand_query.filter(
                            Q(name__icontains='laptop') | Q(name__icontains='notebook') | 
                            Q(name__icontains='macbook') | Q(name__icontains='ultrabook')
                        )
                    elif product_type == 'monitor':
                        cross_brand_query = cross_brand_query.filter(
                            Q(name__icontains='monitor') | Q(name__icontains='display')
                        )
                    elif product_type == 'keyboard':
                        cross_brand_query = cross_brand_query.filter(
                            Q(name__icontains='keyboard') | Q(name__icontains='kb') | Q(name__icontains='typing')
                        )
                    elif product_type == 'mouse':
                        cross_brand_query = cross_brand_query.filter(
                            Q(name__icontains='mouse') | Q(name__icontains='mice') | Q(name__icontains='trackpad') | Q(name__icontains='pointing')
                        )
                    elif product_type == 'accessory':
                        cross_brand_query = cross_brand_query.filter(
                            Q(name__icontains='cable') | Q(name__icontains='cord') | Q(name__icontains='adapter') | 
                            Q(name__icontains='charger') | Q(name__icontains='power') | Q(name__icontains='hub') |
                            Q(name__icontains='dock') | Q(name__icontains='mount') | Q(name__icontains='stand')
                        )
                
                    # Exclude same brand and products we already have
                    if search_brand:
                        cross_brand_query = cross_brand_query.exclude(manufacturer__name__icontains=search_brand)
                
                    if results:
                        existing_ids = [r.id for r in results]
                        cross_brand_query = cross_brand_query.exclude(id__in=existing_ids)
                
                    cross_brand_products = cross_brand_query[:2]  # Limit to 2 cross-brand alternatives
                
                    for product in cross_brand_products:
                        # Check if this is an Amazon product using improved logic
                        is_amazon_product = False
                        
                        # 1. Check if manufacturer is explicitly Amazon/Amazon Marketplace
                        if hasattr(product, 'manufacturer') and product.manufacturer:
                            manufacturer_name = product.manufacturer.name.lower()
                            if 'amazon' in manufacturer_name and ('marketplace' in manufacturer_name or manufacturer_name == 'amazon'):
                                is_amazon_product = True
                        
                        # 2. Check if product source indicates Amazon origin
                        if hasattr(product, 'source') and product.source and 'amazon' in product.source.lower():
                            is_amazon_product = True
                        
                        # 3. Check if product is explicitly marked as placeholder
                        if hasattr(product, 'is_placeholder') and product.is_placeholder:
                            is_amazon_product = True
                    
                        # Get ALL affiliate links (not just Amazon)
                        all_affiliate_links = list(AffiliateLinkModel.objects.filter(
                            product=product
                        ))
                    
                        # Determine relationship category
                        relationship_category = "cross_brand_alternative"
                        if hasattr(product, 'is_demo') and product.is_demo:
                            relationship_category = "cross_brand_demo_alternative"
                        elif is_amazon_product:
                            relationship_category = "cross_brand_amazon_alternative"
                    
                        result = ProductSearchResult(
                            id=product.id,
                            name=product.name,
                            part_number=product.part_number,
                            description=product.description,
                            main_image=product.main_image,
                            manufacturer=product.manufacturer,
                            is_amazon_product=is_amazon_product,
                            is_alternative=True,
                            match_type="cross_brand_alternative",
                            match_confidence=0.7,  # Lower confidence for cross-brand
                            relationship_type="equivalent",
                            relationship_category=relationship_category,
                            margin_opportunity="medium" if not is_amazon_product else "affiliate_only",
                            revenue_type="product_sale" if not is_amazon_product else "affiliate_commission",
                            offers=list(OfferModel.objects.filter(product=product).select_related('vendor')),
                            affiliate_links=all_affiliate_links
                        )
                        result._source_product = product
                        results.append(result)
                
                    debug_logger.info(f"🔍 Found {len(cross_brand_products)} cross-brand {product_type} alternatives")
        
        debug_logger.info(f"🎯 INTELLIGENT SEARCH COMPLETE: {len(results)} results")
        return results
    
    @staticmethod
    def _dynamic_amazon_search_static(search_term):
        """
        REAL: Dynamic Amazon search with real-time affiliate link creation via Puppeteer worker
        
        This:
        1. Triggers Amazon search via Puppeteer worker
        2. Creates affiliate links dynamically 
        3. Returns Amazon alternatives with commission opportunities
        4. Stores results for future use
        """
        debug_logger.info(f"🔍 REAL Amazon search for '{search_term}'")
        
        if not search_term or len(search_term.strip()) < 2:
            debug_logger.warning("Search term too short, skipping Amazon search")
            return []
        
        results = []
        
        try:
            # Import the search function
            from affiliates.tasks import generate_affiliate_url_from_search
            
            # Determine search type based on search term
            search_type = "part_number"
            if search_term and any(char.isalpha() for char in search_term) and ' ' in search_term:
                search_type = "product_name"
            elif search_term and len(search_term) > 15:
                search_type = "general"
            
            # Trigger the Amazon search task
            debug_logger.info(f"🎯 Triggering Amazon search: term='{search_term}', type='{search_type}'")
            task_id, success = generate_affiliate_url_from_search(search_term, search_type)
            
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
                
                # Create error placeholder
                error_result = ProductSearchResult(
                    id="amazon_search_error",
                    title=f"Amazon Search Error",
                    name=f"Amazon Search Error",
                    part_number="ERROR",
                    description=f"Unable to search Amazon for '{search_term}' at this time. Please try again later.",
                    asin="ERROR",
                    is_amazon_product=True,
                    is_alternative=True,
                    match_type="amazon_search_error",
                    match_confidence=0.0,
                    relationship_type="error",
                    relationship_category="amazon_search_error",
                    margin_opportunity="none",
                    revenue_type="error",
                    price="N/A",
                    availability="Search unavailable"
                )
                results.append(error_result)
                
        except Exception as e:
            debug_logger.error(f"❌ Error in dynamic Amazon search: {str(e)}", exc_info=True)
            
            # Create error placeholder
            error_result = ProductSearchResult(
                id="amazon_search_exception",
                title=f"Amazon Search Error",
                name=f"Amazon Search Error", 
                part_number="EXCEPTION",
                description=f"An error occurred while searching Amazon: {str(e)}",
                asin="EXCEPTION",
                is_amazon_product=True,
                is_alternative=True,
                match_type="amazon_search_exception",
                match_confidence=0.0,
                relationship_type="error",
                relationship_category="amazon_search_exception",
                margin_opportunity="none",
                revenue_type="error",
                price="N/A",
                availability="Search failed"
            )
            results.append(error_result)
        
        debug_logger.info(f"🎯 Dynamic Amazon search completed: {len(results)} results")
        return results
    
    @staticmethod
    def _find_relevant_accessories_for_product_static(product_name):
        """Find relevant accessories from internal inventory for cross-sell opportunities"""
        debug_logger.info(f"🎯 ACCESSORIES SEARCH for: {product_name}")
        
        if not product_name:
            return []
        
        results = []
        product_lower = product_name.lower()
        
        # Define accessory mapping based on product type
        accessory_searches = []
        
        if any(laptop_term in product_lower for laptop_term in ['laptop', 'notebook', 'surface', 'macbook', 'thinkpad']):
            accessory_searches = ['laptop power', 'laptop cable', 'laptop adapter', 'laptop charger', 'usb hub', 'laptop stand']
        elif any(desktop_term in product_lower for desktop_term in ['desktop', 'pc', 'computer']):
            accessory_searches = ['pc power', 'computer cable', 'keyboard', 'mouse', 'monitor cable']
        elif any(monitor_term in product_lower for monitor_term in ['monitor', 'display', 'screen']):
            accessory_searches = ['hdmi cable', 'vga cable', 'monitor mount', 'display cable']
        elif any(phone_term in product_lower for phone_term in ['phone', 'iphone', 'smartphone']):
            accessory_searches = ['phone charger', 'usb cable', 'phone case']
        elif any(keyboard_term in product_lower for keyboard_term in ['keyboard', 'kb', 'typing']):
            accessory_searches = ['keyboard stand', 'wrist rest', 'keyboard cable', 'usb hub']
        elif any(mouse_term in product_lower for mouse_term in ['mouse', 'mice', 'trackpad', 'pointing']):
            accessory_searches = ['mouse pad', 'mouse cable', 'wrist rest']
        else:
            # Only suggest very generic accessories for unknown product types
            accessory_searches = ['cable', 'adapter']
        
        # Search for each accessory type
        for accessory_term in accessory_searches[:2]:  # Limit to top 2 types to reduce memory usage
            try:
                # Add more restrictive query to prevent memory issues
                accessories = ProductModel.objects.filter(
                    Q(name__icontains=accessory_term) | Q(description__icontains=accessory_term)
                ).select_related('manufacturer').only(
                    'id', 'name', 'part_number', 'description', 'main_image', 'manufacturer'
                )[:1]  # Reduce to 1 per type to prevent memory issues
                
                for accessory in accessories:
                    # Limit related queries to prevent memory issues
                    offers = list(OfferModel.objects.filter(product=accessory).select_related('vendor')[:2])
                    affiliate_links = list(AffiliateLinkModel.objects.filter(product=accessory)[:2])
                    
                    result = ProductSearchResult(
                        id=accessory.id,
                        name=accessory.name,
                        part_number=accessory.part_number,
                        description=accessory.description,
                        main_image=accessory.main_image,
                        manufacturer=accessory.manufacturer,
                        is_amazon_product=False,
                        is_alternative=False,  # Accessories are not alternatives
                        match_type="accessory_cross_sell",
                        match_confidence=0.7,
                        relationship_type="accessory",
                        relationship_category=f"{accessory_term.replace(' ', '_')}_accessory",
                        margin_opportunity="high",
                        revenue_type="cross_sell_opportunity",
                        offers=offers,
                        affiliate_links=affiliate_links
                    )
                    result._source_product = accessory
                    results.append(result)
                    
            except Exception as e:
                debug_logger.error(f"❌ Accessory search error for '{accessory_term}': {e}")
                # Continue with other accessory types even if one fails
        
        debug_logger.info(f"🎯 Found {len(results)} relevant accessories")
        return results
    
    @staticmethod
    def _create_product_record_for_future_static(part_number, name):
        """
        Create a product record for future monetization opportunities
        This runs as a background task to avoid slowing down the response
        """
        try:
            # Import here to avoid circular imports
            from products.tasks import create_future_product_record
            
            debug_logger.info(f"📝 FUTURE PRODUCT: Queuing creation for part='{part_number}', name='{name}'")
            
            # Queue the task asynchronously
            task_data = {
                'part_number': part_number,
                'name': name,
                'source': 'chrome_extension_universal_search',
                'timestamp': timezone.now().isoformat()
            }
            
            # Use Django Q to queue the task
            from django_q.tasks import async_task
            async_task(
                'products.tasks.create_future_product_record',
                task_data,
                group='future_products',
                timeout=300
            )
            
            debug_logger.info(f"✅ Future product creation queued successfully")
            
        except Exception as e:
            debug_logger.error(f"❌ Error queuing future product creation: {e}")
            # Don't fail the main request if background task fails

    # Keep original instance methods for backward compatibility
    def _handle_non_amazon_product_search(self, partNumber=None, name=None):
        return Query._handle_non_amazon_product_search_static(partNumber, name)
    
    def _search_internal_inventory(self, part_number=None, name=None):
        return Query._search_internal_inventory_static(part_number, name)
        
    def _dynamic_amazon_search(self, search_term):
        return Query._dynamic_amazon_search_static(search_term)
        
    def _find_relevant_accessories_for_product(self, product_name):
        return Query._find_relevant_accessories_for_product_static(product_name)
        
    def _create_product_record_for_future(self, part_number, name):
        return Query._create_product_record_for_future_static(part_number, name)

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

    def resolve_consumer_product_search(self, info, search_term, limit=20):
        """
        Enhanced consumer product search with Amazon API integration
        """
        # Implement the logic to search for consumer products using Amazon API
        # This might involve calling an external service or a custom algorithm
        # For now, we'll just return a placeholder result
        return [
            ProductSearchResult(
                id=f"amazon_search_pending_{search_term}",
                title=f"Amazon Search for '{search_term}' (Processing...)",
                name=f"Amazon Search for '{search_term}' (Processing...)",
                part_number=f"SEARCH_{search_term}",
                description=f"Searching Amazon for products matching '{search_term}'. This may take a few moments...",
                asin=f"SEARCH_{search_term}",
                is_amazon_product=True,
                is_alternative=True,
                match_type="amazon_search_pending",
                match_confidence=0.9,
                relationship_type="equivalent",
                relationship_category="amazon_search_alternative",
                margin_opportunity="affiliate_only",
                revenue_type="affiliate_commission",
                price="Search in progress...",
                availability=f"Amazon search task: {search_term}"
            )
        ]

    def resolve_product_associations(self, info, search_term=None, source_product_id=None, target_product_id=None, association_type=None, limit=10):
        """
        Get product associations for search optimization
        """
        queryset = ProductAssociation.objects.filter(is_active=True)
        
        if search_term:
            queryset = queryset.filter(original_search_term__icontains=search_term)
        
        if source_product_id:
            queryset = queryset.filter(source_product_id=source_product_id)
            
        if target_product_id:
            queryset = queryset.filter(target_product_id=target_product_id)
            
        if association_type:
            queryset = queryset.filter(association_type=association_type)
        
        return queryset.select_related('source_product', 'target_product').order_by('-search_count', '-confidence_score')[:limit]

    def resolve_existing_alternatives(self, info, search_term):
        """
        Check for existing product alternatives based on search term - this is the intelligence!
        """
        from affiliates.views import get_existing_associations
        
        # Use the smart association lookup function
        associations = get_existing_associations(search_term, limit=10)
        
        if associations:
            logger.info(f"🎯 GraphQL: Found {len(associations)} existing alternatives for '{search_term}'")
        else:
            logger.info(f"❌ GraphQL: No existing alternatives found for '{search_term}'")
        
        return associations

    @staticmethod
    def _search_internal_inventory_context_aware_static(amazon_product_name):
        """
        CONTEXT-AWARE SEARCH that leverages rich Amazon product information
        
        Progressive search strategy:
        1. Extract context: brand, product line, category, specs
        2. Search with progressive specificity: 
           - "Apple MacBook Pro" (brand + product)
           - "Apple laptop" (brand + category)
           - "MacBook Pro" (product line only)
           - "laptop" (category fallback)
        3. Prioritize results by relevance
        """
        debug_logger.info(f"🧠 CONTEXT-AWARE SEARCH: {amazon_product_name[:100]}...")
        
        # Step 1: Extract rich context from Amazon product name
        context = Query._extract_product_context_static(amazon_product_name)
        debug_logger.info(f"🔍 Extracted context: {context}")
        
        # Step 2: Build progressive search terms (most specific to least specific)
        search_terms = []
        
        # Most specific: Brand + Product Line
        if context['brand'] and context['product_line']:
            search_terms.append(f"{context['brand']} {context['product_line']}")
        
        # Brand + Category
        if context['brand'] and context['category']:
            search_terms.append(f"{context['brand']} {context['category']}")
        
        # Product Line only
        if context['product_line']:
            search_terms.append(context['product_line'])
        
        # Category fallback
        if context['category']:
            search_terms.append(context['category'])
        
        debug_logger.info(f"🎯 Progressive search terms: {search_terms}")
        
        # Step 3: Execute progressive search
        all_results = []
        seen_product_ids = set()
        
        for i, search_term in enumerate(search_terms):
            debug_logger.info(f"🔍 Pass {i+1}: Searching for '{search_term}'")
            
            # Use existing internal search but track results differently
            pass_results = Query._search_internal_inventory_static(
                part_number=None,
                name=search_term
            )
            
            # Add results, avoiding duplicates and prioritizing by search specificity
            for result in pass_results:
                if hasattr(result, '_source_product') and result._source_product:
                    product_id = result._source_product.id
                    if product_id not in seen_product_ids:
                        # Boost confidence based on search specificity
                        specificity_boost = (len(search_terms) - i) * 0.1
                        if hasattr(result, 'match_confidence'):
                            result.match_confidence = min(1.0, result.match_confidence + specificity_boost)
                        
                        # Add context-aware relationship info
                        result.relationship_category = f"context_match_{search_term.replace(' ', '_').lower()}"
                        result.match_type = f"context_aware_pass_{i+1}"
                        
                        all_results.append(result)
                        seen_product_ids.add(product_id)
                        debug_logger.info(f"✅ Added: {result.name} (confidence: {getattr(result, 'match_confidence', 0.0):.2f})")
            
            # If we found good results in early passes, limit how many more we need
            if i == 0 and len(all_results) >= 3:  # Found 3+ exact brand+product matches
                debug_logger.info(f"🎯 Early termination: Found {len(all_results)} high-quality matches")
                break
            elif i == 1 and len(all_results) >= 5:  # Found 5+ brand matches
                debug_logger.info(f"🎯 Mid termination: Found {len(all_results)} brand matches")
                break
        
        # Step 4: Sort by relevance (confidence score, then relationship category)
        all_results.sort(key=lambda r: (
            getattr(r, 'match_confidence', 0.0),
            'brand_product' in getattr(r, 'relationship_category', ''),  # Prioritize brand+product matches
            'brand' in getattr(r, 'relationship_category', ''),  # Then brand matches
        ), reverse=True)
        
        debug_logger.info(f"🎯 CONTEXT-AWARE SEARCH COMPLETE: {len(all_results)} prioritized results")
        
        # Return top results (limit to avoid overwhelming the response)
        return all_results[:10]
    
    @staticmethod
    def _extract_product_context_static(amazon_product_name):
        """
        Extract structured context from Amazon product names
        
        Returns: {
            'brand': 'Apple',
            'product_line': 'MacBook Pro', 
            'category': 'laptop',
            'specs': ['M4', '14.2-inch', '2024'],
            'original': full_name
        }
        """
        name_lower = amazon_product_name.lower()
        context = {
            'brand': None,
            'product_line': None,
            'category': None,
            'specs': [],
            'original': amazon_product_name
        }
        
        # Brand detection (order matters - check specific before generic)
        brand_patterns = [
            ('Apple', ['apple']),
            ('Dell', ['dell']),
            ('HP', ['hp', 'hewlett']),
            ('Lenovo', ['lenovo', 'thinkpad']),
            ('Microsoft', ['microsoft', 'surface']),
            ('ASUS', ['asus']),
            ('Acer', ['acer']),
            ('Samsung', ['samsung']),
            ('LG', ['lg ']),  # Space to avoid false matches
            ('Sony', ['sony']),
            ('Logitech', ['logitech']),
        ]
        
        for brand_name, patterns in brand_patterns:
            if any(pattern in name_lower for pattern in patterns):
                context['brand'] = brand_name
                break
        
        # Product line detection (more specific patterns)
        product_patterns = [
            ('MacBook Pro', ['macbook pro']),
            ('MacBook Air', ['macbook air']),
            ('MacBook', ['macbook']),  # Fallback after specific MacBook variants
            ('Surface Pro', ['surface pro']),
            ('Surface Laptop', ['surface laptop']),
            ('Surface', ['surface']),  # Fallback
            ('ThinkPad', ['thinkpad']),
            ('XPS', ['xps']),
            ('Inspiron', ['inspiron']),
            ('OptiPlex', ['optiplex']),
            ('iPad Pro', ['ipad pro']),
            ('iPad Air', ['ipad air']),
            ('iPad', ['ipad']),
            ('iPhone', ['iphone']),
        ]
        
        for product_name, patterns in product_patterns:
            if any(pattern in name_lower for pattern in patterns):
                context['product_line'] = product_name
                break
        
        # Category detection (order matters - check specific combos first)
        category_patterns = [
            # Check for combos first before individual components
            ('keyboard_mouse_combo', ['keyboard and mouse', 'mouse and keyboard', 'keyboard + mouse', 'wireless keyboard and mouse', 'keyboard mouse combo']),
            # Then check for individual product types
            ('laptop', ['laptop', 'notebook', 'macbook', 'ultrabook', 'thinkpad', 'surface laptop']),
            ('desktop', ['desktop pc', 'desktop computer', 'pc computer', 'workstation', 'all-in-one']),
            ('monitor', ['monitor', 'display', 'screen', 'lcd', 'led', 'oled']),
            ('gaming', ['gaming laptop', 'gaming desktop', 'gaming monitor', 'gaming pc', 'gaming chair', 'gaming headset']),
            ('printer', ['printer', 'inkjet', 'laserjet', 'multifunction', 'mfp', 'all-in-one printer']),
            ('keyboard', ['keyboard', 'kb']),  # Will only match if combo didn't match first
            ('mouse', ['mouse', 'mice']),  # Will only match if combo didn't match first
            ('tablet', ['tablet', 'ipad', 'surface pro']),
            ('phone', ['phone', 'iphone', 'smartphone', 'android']),
            ('headphones', ['headphones', 'earbuds', 'airpods', 'headset']),
            ('speaker', ['speaker', 'audio', 'soundbar']),
            ('cable', ['cable', 'cord']),
            ('adapter', ['adapter', 'charger']),
            ('stand', ['stand', 'mount']),
        ]
        
        for category_name, patterns in category_patterns:
            if any(pattern in name_lower for pattern in patterns):
                context['category'] = category_name
                break
        
        # Specs extraction (look for common technical specifications)
        import re
        
        # Screen sizes
        screen_matches = re.findall(r'(\d+(?:\.\d+)?)[\'\"]\s*(?:inch|in)?', name_lower)
        if screen_matches:
            context['specs'].extend([f"{size}-inch" for size in screen_matches])
        
        # Processors
        processor_patterns = [
            (r'm[1-4]\s*(?:chip|processor)?', 'Apple Silicon'),
            (r'intel\s*(?:core\s*)?i[3579]', 'Intel Core'),
            (r'amd\s*ryzen', 'AMD Ryzen'),
            (r'intel\s*xeon', 'Intel Xeon'),
        ]
        
        for pattern, proc_type in processor_patterns:
            if re.search(pattern, name_lower):
                context['specs'].append(proc_type)
        
        # Memory/Storage
        memory_matches = re.findall(r'(\d+)\s*gb\s*(?:ram|memory)?', name_lower)
        if memory_matches:
            context['specs'].extend([f"{mem}GB RAM" for mem in memory_matches])
        
        storage_matches = re.findall(r'(\d+)\s*(?:gb|tb)\s*(?:ssd|storage)?', name_lower)
        if storage_matches:
            context['specs'].extend([f"{stor}GB Storage" for stor in storage_matches])
        
        # Year detection
        year_matches = re.findall(r'(20\d{2})', amazon_product_name)  # 2000-2099
        if year_matches:
            context['specs'].extend(year_matches)
        
        return context

    @staticmethod
    def _build_category_specific_filters_static(detected_category):
        """
        Build category-appropriate search filters for high-value discovery.
        Returns None if category doesn't warrant accessory suggestions.
        
        This enables context-aware accessory recommendations:
        - Laptop searches -> laptop accessories (stands, chargers, hubs)
        - Monitor searches -> monitor accessories (mounts, cables)
        - Phone searches -> phone accessories (cases, chargers)
        
        Returns None for categories that don't typically need accessories
        (like keyboards/mice which ARE accessories themselves).
        """
        from django.db.models import Q
        
        if not detected_category:
            debug_logger.info(f"🔍 No category detected, skipping accessory suggestions")
            return None
        
        # Define what accessories make sense for each category
        category_accessory_mapping = {
            'laptop': [
                'laptop stand', 'laptop mount', 'laptop charger', 'laptop power', 
                'usb hub', 'docking station', 'laptop sleeve', 'laptop bag',
                'wireless mouse', 'bluetooth keyboard', 'laptop cooler', 'port replicator',
                'usb-c hub', 'thunderbolt dock', 'laptop riser', 'notebook stand',
                'laptop adapter', 'laptop cable', 'cooling pad'
            ],
            'desktop': [
                'desktop mount', 'keyboard', 'mouse', 'monitor', 'webcam', 
                'speakers', 'microphone', 'usb hub', 'cable management',
                'desktop stand', 'cpu holder', 'monitor arm', 'pc cable',
                'computer cable', 'desktop power', 'pc adapter'
            ],
            'monitor': [
                'monitor mount', 'monitor stand', 'monitor arm', 'monitor riser',
                'hdmi cable', 'displayport cable', 'vga cable', 'dvi cable',
                'cable', 'mount', 'stand', 'arm',  # Broader terms to match actual inventory
                'monitor light', 'screen cleaner', 'dual monitor stand',
                'display cable', 'monitor cable', 'screen mount'
            ],
            'phone': [
                'phone case', 'phone charger', 'wireless charger', 'phone mount',
                'screen protector', 'earbuds', 'phone stand', 'car mount',
                'phone holder', 'charging cable', 'phone adapter', 'mobile charger'
            ],
            'tablet': [
                'tablet case', 'tablet stand', 'stylus', 'tablet charger',
                'keyboard case', 'screen protector', 'tablet mount', 'apple pencil',
                'tablet adapter', 'tablet cable', 'tablet holder'
            ],
            # NEW: Add gaming category
            'gaming': [
                'gaming mouse', 'gaming keyboard', 'gaming headset', 'gaming chair',
                'gaming mousepad', 'gaming cable', 'gaming adapter', 'rgb lighting',
                'gaming stand', 'controller', 'gaming hub'
            ],
            # NEW: Add printer category  
            'printer': [
                'printer cable', 'usb cable', 'printer stand', 'paper tray',
                'ink cartridge', 'toner', 'printer adapter', 'print server'
            ]
            # Note: We intentionally DON'T include mappings for:
            # - keyboard, mouse, keyboard_mouse_combo (they ARE accessories, not things that need accessories)
            # - Individual keyboard/mouse products don't typically need their own accessories
        }
        
        accessory_terms = category_accessory_mapping.get(detected_category)
        
        if not accessory_terms:
            debug_logger.info(f"🔍 Category '{detected_category}' doesn't warrant accessory suggestions")
            return None
        
        debug_logger.info(f"🎯 Building accessory filters for '{detected_category}': {len(accessory_terms)} terms")
        
        # Build OR query for all relevant accessory terms
        accessory_filter = Q()
        for term in accessory_terms:
            accessory_filter |= Q(name__icontains=term)
        
        return accessory_filter

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
    
    # Affiliate-generation workflow flags
    needs_affiliate_generation = graphene.Boolean()
    task_id = graphene.String()
    is_placeholder = graphene.Boolean()
    
    # CamelCase aliases for frontend compatibility
    needsAffiliateGeneration = graphene.Boolean()
    taskId = graphene.String()
    isPlaceholder = graphene.Boolean()
    
    # Resolvers for camelCase aliases
    def resolve_needsAffiliateGeneration(self, info):
        return getattr(self, 'needs_affiliate_generation', None)
    
    def resolve_taskId(self, info):
        return getattr(self, 'task_id', None)

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

    def resolve_isPlaceholder(self, info):
        return getattr(self, 'is_placeholder', False)

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
    IMPORTANT: Only creates Amazon affiliate links for actual Amazon products.
    Returns the list of all affiliate links for the product.
    """
    # Check for existing Amazon affiliate link first
    amazon_link = AffiliateLinkModel.objects.filter(
        product=product, 
        platform='amazon'
    ).first()
    
    # Get all affiliate links for this product
    product_links = list(AffiliateLinkModel.objects.filter(product=product))
    
    # CRITICAL: Only create Amazon affiliate links for actual Amazon products
    # Don't create Amazon links for CDW, Best Buy, or other supplier products
    is_amazon_product = False
    
    # Check if this is actually an Amazon product by looking at:
    # 1. Source URL contains amazon.com
    # 2. Existing Amazon affiliate links
    # 3. Product source indicates it came from Amazon
    
    if hasattr(product, 'source_url') and product.source_url and 'amazon.com' in product.source_url:
        is_amazon_product = True
    elif amazon_link:  # Already has an Amazon link, so it's likely an Amazon product
        is_amazon_product = True
    elif hasattr(product, 'source') and product.source and 'amazon' in product.source.lower():
        is_amazon_product = True
    
    # Check if the product was imported from Amazon by looking at the main_image URL
    if hasattr(product, 'main_image') and product.main_image:
        if 'amazon.com' in product.main_image or 'images-amazon.com' in product.main_image:
            is_amazon_product = True
        elif 'cdw.com' in product.main_image or 'bestbuy.com' in product.main_image:
            is_amazon_product = False  # Explicitly not an Amazon product
    
    # If we don't have an Amazon link and this IS an Amazon product, create one
    if not amazon_link and is_amazon_product and product.part_number:
        try:
            logger.info(f"Creating Amazon affiliate link for Amazon product {product.id} with part number {product.part_number}")
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
    elif not amazon_link and not is_amazon_product:
        debug_logger.info(f"🚫 Skipping Amazon affiliate link creation for non-Amazon product: {product.name} (ID: {product.id})")
    
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
    stop_words.update(['the', 'and', 'with', 'for', 'this', 'that', 'from', 'to', 'in', 'of', 'a', 'an'])
    
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
    """
    Handle affiliate link creation for a product with an ASIN
    """
    # Check if we already have an affiliate link for this ASIN
    existing_link = AffiliateLinkModel.objects.filter(
        product=product,
        platform='amazon',
        platform_id=asin
    ).first()
    
    if existing_link:
        debug_logger.info(f"🔗 Found existing affiliate link for ASIN {asin}: {existing_link.affiliate_url}")
        return existing_link
    
    # Create new affiliate link
    debug_logger.info(f"🆕 Creating new affiliate link for ASIN {asin}")
    affiliate_link = AffiliateLinkModel.objects.create(
        product=product,
        platform='amazon',
        platform_id=asin,
        original_url=url or f"https://amazon.com/dp/{asin}",
        affiliate_url='',  # Will be populated by background task
        is_active=True
    )
    
    # Queue background task to generate the affiliate URL
    try:
        task_result = async_task('affiliates.tasks.generate_amazon_affiliate_url', asin)
        debug_logger.info(f"🚀 Queued affiliate task: {task_result}")
    except Exception as e:
        debug_logger.error(f"❌ Failed to queue affiliate task: {e}")
    
    return affiliate_link

def wait_for_affiliate_completion(asin, timeout_seconds=30):
    """
    Wait for affiliate link generation to complete, with timeout.
    Returns (affiliate_link, completed) tuple.
    """
    import time
    from django.utils import timezone
    
    start_time = time.time()
    debug_logger.info(f"⏳ Waiting up to {timeout_seconds}s for affiliate link completion: {asin}")
    
    while time.time() - start_time < timeout_seconds:
        # Check if affiliate link is complete
        affiliate_link = AffiliateLinkModel.objects.filter(
            platform='amazon',
            platform_id=asin
        ).first()
        
        if affiliate_link and affiliate_link.affiliate_url and affiliate_link.affiliate_url.strip():
            debug_logger.info(f"✅ Affiliate link completed in {time.time() - start_time:.1f}s: {affiliate_link.affiliate_url[:50]}...")
            return affiliate_link, True
        
        # Wait a bit before checking again
        time.sleep(0.5)
    
    debug_logger.warning(f"⏰ Affiliate link generation timed out after {timeout_seconds}s for ASIN: {asin}")
    return affiliate_link if 'affiliate_link' in locals() else None, False

# Helper functions for ASIN search
def ensure_affiliate_link_exists(asin):
    """
    OPTIMIZED: Always ensure we have an affiliate link for this ASIN
    
    COMBINATION APPROACH:
    - Caching to avoid repeated DB hits
    - Processing state tracking to prevent duplicate tasks  
    - Comprehensive logging to track duplicate prevention
    - Background task safety checks
    """
    import redis
    from django.utils import timezone
    from datetime import timedelta
    
    # STEP 1: Check Redis cache first (5-minute cache)
    try:
        redis_kwargs = get_redis_connection()
        r = redis.Redis(**redis_kwargs)
        cache_key = f"affiliate_check:{asin}"
        cached_result = r.get(cache_key)
        
        if cached_result:
            debug_logger.info(f"🚀 CACHE HIT: ASIN {asin} - returning cached affiliate link")
            try:
                link_id = int(cached_result)
                return AffiliateLinkModel.objects.get(id=link_id)
            except (ValueError, AffiliateLinkModel.DoesNotExist):
                debug_logger.warning(f"⚠️ Invalid cached link ID {cached_result}, proceeding with DB check")
                r.delete(cache_key)  # Clear bad cache
    except Exception as e:
        debug_logger.warning(f"⚠️ Redis cache check failed: {e}")
    
    # STEP 2: Check database for existing affiliate link
    existing_link = AffiliateLinkModel.objects.filter(
        platform='amazon',
        platform_id=asin
    ).first()
    
    if existing_link:
        debug_logger.info(f"📋 DB CHECK: Found existing affiliate link {existing_link.id} for ASIN {asin}")
        
        # STEP 2A: Check if link is already complete
        if existing_link.affiliate_url and existing_link.affiliate_url.strip():
            debug_logger.info(f"✅ COMPLETE LINK: Affiliate URL already exists - {existing_link.affiliate_url[:50]}...")
            
            # Cache the complete link for 5 minutes
            try:
                r.setex(cache_key, 300, existing_link.id)  # 5 minutes
                debug_logger.info(f"💾 CACHED: Complete affiliate link for ASIN {asin}")
            except Exception as e:
                debug_logger.warning(f"⚠️ Failed to cache complete link: {e}")
            
            return existing_link
        
        # STEP 2B: Check if processing is already in progress
        if existing_link.is_processing:
            # Check if processing has been running too long (over 10 minutes = stuck)
            if existing_link.processing_started_at:
                time_since_start = timezone.now() - existing_link.processing_started_at
                if time_since_start > timedelta(minutes=10):
                    debug_logger.warning(f"⏰ STUCK TASK: Processing stuck for {time_since_start}, resetting...")
                    existing_link.is_processing = False
                    existing_link.processing_started_at = None
                    existing_link.save(update_fields=['is_processing', 'processing_started_at'])
                else:
                    debug_logger.info(f"⏳ PROCESSING: Task already in progress for {time_since_start} - avoiding duplicate")
                    return existing_link
            else:
                debug_logger.warning(f"🔧 FIXING: is_processing=True but no start time, resetting...")
                existing_link.is_processing = False
                existing_link.save(update_fields=['is_processing'])
    
    # STEP 3: Create new affiliate link if none exists
    if not existing_link:
        debug_logger.info(f"🆕 CREATING: New affiliate link for ASIN {asin}")
        try:
            # Create a placeholder product for the ASIN if one doesn't exist
            # This ensures the affiliate link has a valid product relationship
            placeholder_product = None
            try:
                placeholder_product = ProductModel.objects.get(part_number=asin)
                debug_logger.info(f"📦 Found existing placeholder product for ASIN {asin}")
            except ProductModel.DoesNotExist:
                # Create a basic placeholder product. Manufacturer is required so ensure an "Amazon" manufacturer exists.
                from django.utils.text import slugify
                from products.models import Manufacturer as ManufacturerModel

                amazon_manufacturer, _ = ManufacturerModel.objects.get_or_create(
                    name="Amazon",
                    defaults={
                        "slug": "amazon",
                        "website": "https://www.amazon.com"
                    }
                )

                placeholder_product = ProductModel.objects.create(
                    name=f"Amazon Product {asin}",
                    slug=f"amazon-product-{asin.lower()}",
                    part_number=asin,
                    description=f"Amazon product with ASIN {asin}",
                    manufacturer=amazon_manufacturer,
                    status='pending',
                    source='amazon',
                    is_placeholder=True
                )
                debug_logger.info(f"📦 Created placeholder product {placeholder_product.id} for ASIN {asin}")
            
            existing_link = AffiliateLinkModel.objects.create(
                product=placeholder_product,  # Now we have a valid product
                platform='amazon',
                platform_id=asin,
                original_url=f"https://amazon.com/dp/{asin}",
                affiliate_url='',  # Will be populated by task
                is_active=True,
                is_processing=False  # Let the background task set processing state
            )
            debug_logger.info(f"📝 CREATED: New affiliate link {existing_link.id} for ASIN {asin}")
        except Exception as e:
            debug_logger.error(f"❌ CREATION FAILED: {e}")
            return None
    else:
        # STEP 3A: Update existing incomplete link to processing state
        debug_logger.info(f"🔄 UPDATING: Setting existing link {existing_link.id} to processing state")
        existing_link.is_processing = True
        existing_link.processing_started_at = timezone.now()
        existing_link.save(update_fields=['is_processing', 'processing_started_at'])
    
    # STEP 4: Queue background task (only after securing processing state)
    debug_logger.info(f"🚀 QUEUING: Background task for ASIN {asin}")
    try:
        task_result = async_task('affiliates.tasks.generate_standalone_amazon_affiliate_url', asin)
        debug_logger.info(f"✅ TASK QUEUED: {task_result} for affiliate link {existing_link.id}")
    except Exception as e:
        debug_logger.error(f"❌ TASK QUEUE FAILED: {e}")
        # Reset processing state if task creation failed
        existing_link.is_processing = False
        existing_link.processing_started_at = None
        existing_link.save(update_fields=['is_processing', 'processing_started_at'])
        return existing_link
    
    # STEP 5: Cache the processing link for a shorter time (1 minute) 
    try:
        r.setex(cache_key, 60, existing_link.id)  # 1 minute for processing links
        debug_logger.info(f"💾 CACHED: Processing affiliate link for ASIN {asin}")
    except Exception as e:
        debug_logger.warning(f"⚠️ Failed to cache processing link: {e}")
    
    return existing_link

def get_amazon_product_by_asin(asin):
    """Find the Amazon product we created for this ASIN"""
    
    # Method 1: Look for affiliate link with this ASIN
    affiliate_link = AffiliateLinkModel.objects.filter(
        platform='amazon',
        platform_id=asin
    ).select_related('product').first()
    
    if affiliate_link and affiliate_link.product:
        # CRITICAL FIX: Prefer non-placeholder products
        if not getattr(affiliate_link.product, 'is_placeholder', False):
            debug_logger.info(f"📦 Found non-placeholder Amazon product via affiliate link: {affiliate_link.product.name}")
            return affiliate_link.product
        else:
            debug_logger.info(f"⚠️ Affiliate link points to placeholder, looking for non-placeholder alternative...")
            # Look for non-placeholder alternative with same ASIN
            non_placeholder = ProductModel.objects.filter(
                part_number=asin, 
                is_placeholder=False
            ).first()
            if non_placeholder:
                debug_logger.info(f"✅ Found non-placeholder alternative: {non_placeholder.name}")
                # CRITICAL: Check if non-placeholder already has an Amazon affiliate link
                existing_non_placeholder_link = AffiliateLinkModel.objects.filter(
                    product=non_placeholder,
                    platform='amazon',
                    platform_id=asin
                ).first()
                
                if existing_non_placeholder_link:
                    debug_logger.info(f"🔗 Non-placeholder already has affiliate link, using that one")
                    return non_placeholder
                else:
                    # Safe to update the affiliate link
                    debug_logger.info(f"🔗 Updating affiliate link to point to real product")
                    try:
                        affiliate_link.product = non_placeholder
                        affiliate_link.save()
                        debug_logger.info(f"✅ Successfully updated affiliate link")
                        return non_placeholder
                    except Exception as e:
                        debug_logger.error(f"❌ Failed to update affiliate link: {e}")
                        # Return the non-placeholder product anyway since it exists
                        return non_placeholder
            else:
                debug_logger.warning(f"⚠️ No non-placeholder found, returning placeholder: {affiliate_link.product.name}")
                return affiliate_link.product  # Return placeholder as fallback
    
    # Method 2: Look for non-placeholder product with ASIN as part number
    try:
        # CRITICAL FIX: Prefer non-placeholder products
        product = ProductModel.objects.filter(part_number=asin, is_placeholder=False).first()
        if product:
            debug_logger.info(f"📦 Found non-placeholder Amazon product via part number: {product.name}")
            return product
        
        # Fallback to placeholder if no non-placeholder exists
        placeholder_product = ProductModel.objects.get(part_number=asin)
        debug_logger.info(f"📦 Found placeholder Amazon product via part number: {placeholder_product.name} (placeholder={placeholder_product.is_placeholder})")
        return placeholder_product
    except ProductModel.DoesNotExist:
        pass
    
    # Method 3: Look for product name containing ASIN (prefer non-placeholder)
    products_with_asin = ProductModel.objects.filter(
        Q(name__icontains=asin) | Q(description__icontains=asin)
    ).order_by('is_placeholder')  # Non-placeholder products first
    
    product = products_with_asin.first()
    if product:
        debug_logger.info(f"📦 Found Amazon product via name/description: {product.name} (placeholder={getattr(product, 'is_placeholder', False)})")
        return product
    
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