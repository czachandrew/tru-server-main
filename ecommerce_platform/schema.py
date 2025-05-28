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
        term=graphene.String(required=True),
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
            totalCount=total_count,
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
        try:
            # Find the product by part number
            product = ProductModel.objects.get(part_number=part_number)
            
            # If ASIN is provided, check for Amazon affiliate link
            if asin:
                try:
                    # Try to find existing affiliate link
                    affiliate_link = AffiliateLinkModel.objects.get(
                        product=product,
                        platform='amazon',
                        platform_id=asin
                    )
                    
                    return ProductExistsResponse(
                        exists=True,
                        product=product,
                        affiliate_link=affiliate_link,
                        needs_affiliate_generation=False,
                        message="Product and affiliate link found"
                    )
                    
                except AffiliateLinkModel.DoesNotExist:
                    # Create new affiliate link
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

                    async_task('affiliates.tasks.generate_amazon_affiliate_url', 
                              affiliate_link.id, asin)
                    
                    return ProductExistsResponse(
                        exists=True,
                        product=product,
                        affiliate_link=affiliate_link,
                        needs_affiliate_generation=True,
                        message="Product found. Affiliate link generation initiated."
                    )
            
            # If no ASIN provided, just return the product
            return ProductExistsResponse(
                exists=True,
                product=product,
                affiliate_link=None,
                needs_affiliate_generation=False,
                message="Product found in database"
            )
            
        except ProductModel.DoesNotExist:
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

    def resolve_products_search(self, info, term, asin=None, max_price=None, **kwargs):
        """
        Search for products in the database using the search term or part number.
        """
        # Log incoming request data
        debug_logger.info(f"Incoming request data: term={term}, asin={asin}, max_price={max_price}, kwargs={kwargs}")

        # Use the built-in filter fields from DjangoFilterConnectionField
        part_number = kwargs.get('part_number_Iexact', None) or kwargs.get('part_number_Icontains', None)
        manufacturer_id = kwargs.get('manufacturer_Id', None)
        
        debug_logger.info(f"Extracted filters - part_number: {part_number}, manufacturer_id: {manufacturer_id}")
        
        # Start with all products
        qs = ProductModel.objects.all().order_by('name')
        
        # STEP 1: Handle ASIN for affiliate links
        if asin:
            debug_logger.info(f"Checking affiliate links for ASIN: {asin}")
            affiliate_links = AffiliateLinkModel.objects.filter(platform_id=asin, platform='amazon')
            if not affiliate_links.exists():
                debug_logger.info(f"No existing affiliate link for ASIN: {asin}, creating new link")
                try:
                    # Pass only the ASIN to the task function
                    async_task('affiliates.tasks.generate_standalone_amazon_affiliate_url', asin)  # Replace with actual URL if needed
                    debug_logger.info(f"Created affiliate link generation task for ASIN: {asin}")
                except Exception as e:
                    debug_logger.error(f"Error creating affiliate link task for ASIN: {asin}: {str(e)}")
            else:
                debug_logger.info(f"Existing affiliate link found for ASIN: {asin}")

        # STEP 2: Try exact part number match if provided
        if part_number:
            debug_logger.info(f"Searching for exact match on provided part number: {part_number}")
            part_match = ProductModel.objects.filter(part_number__iexact=part_number).first()
            if part_match:
                debug_logger.info(f"FOUND EXACT PART NUMBER MATCH: {part_match.id} - {part_match.name}")
                # Log detailed product information
                debug_logger.info(f"Exact Match Details: ID={part_match.id}, Name={part_match.name}, Part Number={part_match.part_number}, Manufacturer={part_match.manufacturer.name if part_match.manufacturer else 'None'}, Description={part_match.description[:100]}...")
                # Log the response structure before returning
                response = [{
                    'product_id': part_match.id,
                    'name': part_match.name,
                    'part_number': part_match.part_number,
                    'manufacturer': part_match.manufacturer.name if part_match.manufacturer else 'None',
                    'offers': [{'price': offer.selling_price, 'vendor': offer.vendor.name} for offer in OfferModel.objects.filter(product=part_match)],
                    'affiliate_links': [{'url': link.url} for link in AffiliateLinkModel.objects.filter(product=part_match)],
                }]
                debug_logger.info(f"Response structure for exact part number match: {json.dumps(response, indent=2)}")
                return response
        
        # STEP 3: If part_number wasn't provided or didn't match, try to extract from term
        extracted_part_number = None
        if term and not part_number:
            # Extract potential part numbers from the term
            paren_matches = re.findall(r'\(([A-Za-z0-9\-_]+)\)', term)
            if paren_matches:
                extracted_part_number = paren_matches[0]
                debug_logger.info(f"Extracted part number from parentheses: {extracted_part_number}")
                
                # Try exact match with the extracted part number
                part_match = ProductModel.objects.filter(part_number__iexact=extracted_part_number).first()
                if part_match:
                    debug_logger.info(f"FOUND MATCH FOR EXTRACTED PART NUMBER: {part_match.id} - {part_match.name}")
                    # Log detailed product information
                    debug_logger.info(f"Exact Match Details: ID={part_match.id}, Name={part_match.name}, Part Number={part_match.part_number}, Manufacturer={part_match.manufacturer.name if part_match.manufacturer else 'None'}, Description={part_match.description[:100]}...")
                    # Log the response structure before returning
                    response = [{
                        'product_id': part_match.id,
                        'name': part_match.name,
                        'part_number': part_match.part_number,
                        'manufacturer': part_match.manufacturer.name if part_match.manufacturer else 'None',
                        'offers': [{'price': offer.selling_price, 'vendor': offer.vendor.name} for offer in OfferModel.objects.filter(product=part_match)],
                        'affiliate_links': [{'url': link.url} for link in AffiliateLinkModel.objects.filter(product=part_match)],
                    }]
                    debug_logger.info(f"Response structure for exact match: {json.dumps(response, indent=2)}")
                    return response
                
                # Use icontains for more flexible matching
                debug_logger.info(f"Searching for products with part number containing: {extracted_part_number}")
                qs = qs.filter(part_number__icontains=extracted_part_number)
        
        # STEP 4: Use manufacturer filtering if provided
        manufacturer_filter_applied = False
        if manufacturer_id:
            debug_logger.info(f"Filtering by provided manufacturer: {manufacturer_id}")
            qs = qs.filter(manufacturer__id=manufacturer_id)
            manufacturer_filter_applied = True
        
        # STEP 5: Use term-based search as final fallback
        if term:
            search_term = term.lower()
            
            # If we have an extracted part but no direct match, try to find similar products
            if extracted_part_number and not manufacturer_filter_applied:
                manufacturers = ["apc", "schneider", "dell", "hp", "lenovo", "apple", "samsung", "logitech", 
                              "microsoft", "cisco", "netgear", "asus", "intel", "amd", "corsair", 
                              "belkin", "tripp lite", "sony", "lg", "western digital", "seagate"]
                
                for mfr in manufacturers:
                    if mfr in search_term:
                        debug_logger.info(f"Extracted manufacturer from term: {mfr}")
                        mfr_qs = qs.filter(manufacturer__name__icontains=mfr)
                        if len(extracted_part_number) >= 4:
                            debug_logger.info(f"Searching for products with part number containing: {extracted_part_number}")
                            mfr_part_qs = mfr_qs.filter(part_number__icontains=extracted_part_number)
                            if mfr_part_qs.exists():
                                debug_logger.info(f"Found {mfr_part_qs.count()} products matching manufacturer and part number")
                                # Collect products for response
                                qs = mfr_part_qs
                                break
            # Extract significant terms from the database
            significant_terms = get_significant_terms()
            
            # Analyze the search query to find matching significant terms
            words_in_search = set(re.findall(r'\b\w+\b', search_term))
            
            # Find significant terms present in the search query
            matching_terms = [word for word in words_in_search if word in significant_terms]
            matching_terms.sort(key=lambda x: significant_terms[x], reverse=True)
            
            debug_logger.info(f"Found {len(matching_terms)} significant terms in search: {matching_terms[:5]}")
            
            # Build term queries based on matching significant terms
            term_queries = Q()
            for term in matching_terms[:5]:  # Use top 5 most significant terms
                term_queries |= Q(name__icontains=term) | Q(description__icontains=term)
            
            # Apply the term filtering
            if term_queries:
                qs = qs.filter(term_queries)
                debug_logger.info(f"Applied term-based filtering, resulting in {qs.count()} products")
        
        # STEP 6: Apply price filter
        if max_price is not None:
            from decimal import Decimal
            try:
                max_price_decimal = Decimal(str(max_price))
                qs = qs.filter(offers__selling_price__lte=max_price_decimal).distinct()
            except (ValueError, TypeError):
                pass
        
        # STEP 7: Handle affiliate link creation if no products found
        qs = qs.distinct()
        product_count = qs.count()
        debug_logger.info(f"Found {product_count} products matching the search criteria")
        
        if product_count == 0:
            try:
                debug_logger.info(f"No compatible products found, creating affiliate link for original product")
                
                # Use provided ASIN if available
                if not part_number and extracted_part_number:
                    if len(extracted_part_number) == 10:
                        debug_logger.info(f"Using extracted part number as potential ASIN: {extracted_part_number}")
                        from django_q.tasks import async_task
                        import uuid
                        task_id = f"amazon-{uuid.uuid4().hex[:8]}"
                        result = async_task('affiliates.tasks.generate_standalone_amazon_affiliate_url', 
                                   extracted_part_number)
                        debug_logger.info(f"Created affiliate link generation task {task_id} for potential ASIN")
            except Exception as e:
                debug_logger.error(f"Error creating affiliate link task: {str(e)}")
        
        # Detailed logging for results
        if product_count > 0:
            debug_logger.info(f"==== SEARCH RESULTS ====")
            debug_logger.info(f"Found {product_count} matching products:")
            
            for i, product in enumerate(qs[:10]):
                offers = list(OfferModel.objects.filter(product=product).select_related('vendor'))
                
                debug_logger.info(f"RESULT #{i+1}: Product ID: {product.id}")
                debug_logger.info(f"  - Name: {product.name}")
                debug_logger.info(f"  - Part Number: {product.part_number}")
                debug_logger.info(f"  - Manufacturer: {product.manufacturer.name if product.manufacturer else 'None'}")
                debug_logger.info(f"  - Description: {product.description[:100]}..." if product.description else "  - Description: None")
                
                debug_logger.info(f"  - Offers: {len(offers)}")
                for offer in offers:
                    debug_logger.info(f"    * Price: ${offer.selling_price}, Vendor: {offer.vendor.name if offer.vendor else 'None'}")
                
                affiliate_links = list(AffiliateLinkModel.objects.filter(product=product))
                debug_logger.info(f"  - Affiliate Links: {len(affiliate_links)}")
                for link in affiliate_links:
                    debug_logger.info(f"    * {link.platform}: {link.original_url}")
            
            if product_count > 10:
                debug_logger.info(f"... and {product_count - 10} more products (truncated log)")
        else:
            debug_logger.info("NO PRODUCTS FOUND IN DATABASE")
        
        debug_logger.info(f"==== PRODUCT SEARCH END ====")
        
        # Log the search results
        debug_logger.info(f"Found {qs.count()} products matching the search criteria")

        # Prepare the response
        response = []
        for product in qs:
            offers = OfferModel.objects.filter(product=product)
            affiliate_links = AffiliateLinkModel.objects.filter(product=product)
            
            response.append({
                'product_id': product.id,
                'name': product.name,
                'part_number': product.part_number,
                'manufacturer': product.manufacturer.name if product.manufacturer else 'None',
                'offers': [{'price': offer.selling_price, 'vendor': offer.vendor.name} for offer in offers],
                'affiliate_links': [{'url': link.url} for link in affiliate_links],
            })
            debug_logger.info(f"Complete response structure in loop: {json.dumps(response, indent=2)}")

        # Log the complete response structure
            debug_logger.info(f"Complete response structure: {json.dumps(response, indent=2)}")

        return response

    def resolve_search_by_asin(self, info, asin, limit=10):
        """
        Find products that have affiliate links with the specified Amazon ASIN
        """
        debug_logger.error(f"Searching for products with ASIN: {asin}")
        
        # Find affiliate links with the provided ASIN
        direct_match_links = AffiliateLinkModel.objects.filter(
            platform='amazon',
            platform_id=asin
        )
        
        debug_logger.error(f"Direct match query found {direct_match_links.count()} links for ASIN={asin}")
        
        # If no direct matches, try with flexible matching
        if direct_match_links.count() == 0:
            cleaned_asin = asin.strip().upper()
            debug_logger.error(f"Trying flexible matching with cleaned ASIN: {cleaned_asin}")
            
            direct_match_links = AffiliateLinkModel.objects.filter(
                platform='amazon'
            ).filter(
                models.Q(platform_id__iexact=asin) |
                models.Q(platform_id__iexact=cleaned_asin) |
                models.Q(platform_id__contains=cleaned_asin) |
                models.Q(original_url__contains=cleaned_asin)
            )
            
            debug_logger.error(f"Flexible match found {direct_match_links.count()} links")
        
        # Collect product data
        results = []
        seen_product_ids = set()
        
        for link in direct_match_links:
            try:
                product = link.product
                debug_logger.error(f"Processing product: ID={product.id}, Name={product.name}")
                
                if product.id in seen_product_ids:
                    debug_logger.error(f"Skipping duplicate product ID: {product.id}")
                    continue
                    
                seen_product_ids.add(product.id)
                
                # Get ALL affiliate links for this product
                product_links = list(AffiliateLinkModel.objects.filter(product=product))
                debug_logger.error(f"Found {len(product_links)} affiliate links for product {product.id}")
                
                # Get ALL offers for this product
                product_offers = list(OfferModel.objects.filter(product=product).select_related('vendor'))
                debug_logger.error(f"Found {len(product_offers)} offers for product {product.id}")
                
                # Create a complete result with all related data
                result = ProductSearchResult(
                    id=product.id,
                    name=product.name,
                    part_number=product.part_number,
                    description=product.description,
                    main_image=product.main_image,
                    manufacturer=product.manufacturer,
                    affiliate_links=product_links,
                    offers=product_offers
                )
                
                # Log the structure to ensure it matches expectations
                debug_logger.error(f"Created ProductSearchResult for {product.id} with name={result.name}, part_number={result.part_number}")
                
                results.append(result)
                debug_logger.error(f"Added complete product to results: {product.id}")
                
                if len(results) >= limit:
                    break
                    
            except Exception as e:
                debug_logger.error(f"Error processing link ID={link.id}: {str(e)}")
        
        # Log what we found
        debug_logger.error(f"Returning {len(results)} complete results for ASIN: {asin}")
        
        # Return the complete results
        return results
    
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
            
            results.append(ProductSearchResult(
                id=product.id,
                name=product.name,
                part_number=product.part_number,
                description=product.description,
                main_image=product.main_image,
                manufacturer=product.manufacturer,
                affiliate_links=product_links,
                offers=product_offers
            ))
            
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
            
            results.append(ProductSearchResult(
                id=product.id,
                name=product.name,
                part_number=product.part_number,
                description=product.description,
                main_image=product.main_image,
                manufacturer=product.manufacturer,
                affiliate_links=product_links,
                offers=product_offers
            ))
            
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
        
        # Create affiliate link for Amazon 
        # Make sure this is doing its job
        if input.asin and input.url:
            logger.info(f"Creating affiliate link with ASIN: {input.asin} for product: {product.id}")
            affiliate_link = AffiliateLinkModel(
                product=product,
                platform='amazon',
                platform_id=input.asin,
                original_url=input.url,
                affiliate_url='',  # Will be populated by background task
                is_active=True
            )
            affiliate_link.save()
            
            # Async task to generate actual affiliate URL - make sure this task works
            from django_q.tasks import async_task
            task = async_task('affiliates.tasks.generate_amazon_affiliate_url', 
                      affiliate_link.id, input.asin)
            
            logger.info(f"Queued affiliate link generation task: {task}")
        else:
            # If no ASIN but we have a part number, use that as fallback
            logger.info(f"No ASIN provided, using part number {product.part_number} for affiliate link")
            affiliate_link = AffiliateLinkModel(
                product=product,
                platform='amazon',
                platform_id=product.part_number,
                original_url=f"https://www.amazon.com/dp/{product.part_number}",
                affiliate_url='',  # Will be populated by background task
                is_active=True
            )
            affiliate_link.save()
            
            # Async task to generate actual affiliate URL
            from django_q.tasks import async_task
            task = async_task('affiliates.tasks.generate_amazon_affiliate_url', 
                      affiliate_link.id, product.part_number)
            
            logger.info(f"Queued affiliate link generation task: {task}")
        
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
class ProductConnection(relay.Connection):
    class Meta:
        node = ProductType
    
    total_count = graphene.Int()
    
    @staticmethod
    def resolve_total_count(root, info, **kwargs):
        return root.length

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
    """Wrapper type for product search results"""
    id = graphene.ID()
    name = graphene.String()
    part_number = graphene.String()
    description = graphene.String()
    main_image = graphene.String()
    manufacturer = graphene.Field(ManufacturerType)
    affiliate_links = graphene.List(AffiliateLinkType)
    offers = graphene.List(OfferType)
    
    # Add any other fields that your client needs

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

schema = graphene.Schema(query=Query, mutation=Mutation)