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

from products.models import Product as ProductModel, Category, Manufacturer as ManufacturerModel
from offers.models import Offer as OfferModel
from vendors.models import Vendor
from affiliates.models import AffiliateLink as AffiliateLinkModel
from store.models import Cart, CartItem
from ecommerce_platform.graphql.types.product import Product, Manufacturer
from .graphql.types.user import UserType
from .graphql.mutations.auth import AuthMutation
from .graphql.mutations.product import ProductMutation
from .graphql.mutations.affiliate import AffiliateMutation, CreateAmazonAffiliateLink
from .graphql.mutations.cart import CartMutation
from graphql_jwt.decorators import login_required
from graphql_jwt.middleware import JSONWebTokenMiddleware
from users.models import UserProfile

# Custom Scalars
from graphene.types.scalars import Scalar
from graphene.types.datetime import DateTime

# Import the GraphQL types from your types directory
from ecommerce_platform.graphql.types.affiliate import AffiliateLinkType
from ecommerce_platform.graphql.types.offer import OfferType

User = get_user_model()

logger = logging.getLogger(__name__)

class JSONScalar(Scalar):
    """JSON Scalar Type"""
    @staticmethod
    def serialize(value):
        return value
    
    @staticmethod
    def parse_literal(node):
        return node.value
    
    @staticmethod
    def parse_value(value):
        return json.loads(value)

# Type Definitions
class Product(DjangoObjectType):
    class Meta:
        model = ProductModel
        fields = "__all__"
        name = "Product"
    
    # GraphQL expects camelCase but Django uses snake_case
    mainImage = graphene.String(source='main_image')
    additionalImages = graphene.List(graphene.String, source='additional_images')
    partNumber = graphene.String(source='part_number')
    dimensions = graphene.Field('ecommerce_platform.schema.Dimensions')
    
    def resolve_dimensions(self, info):
        return self.dimensions or {}

class CategoryType(DjangoObjectType):
    class Meta:
        model = Category
        fields = "__all__"

class ManufacturerType(DjangoObjectType):
    class Meta:
        model = ManufacturerModel
        fields = "__all__"

# class OfferType(DjangoObjectType):
#     class Meta:
#         model = Offer
#         fields = "__all__"

# class VendorType(DjangoObjectType):
#     class Meta:
#         model = Vendor
#         fields = "__all__"

class AffiliateLinkType(DjangoObjectType):
    class Meta:
        model = AffiliateLinkModel
        fields = "__all__"

class CartType(DjangoObjectType):
    class Meta:
        model = Cart
        fields = "__all__"
    
    total_items = graphene.Int()
    total_price = graphene.Float()
    
    def resolve_total_items(self, info):
        return sum(item.quantity for item in self.items.all())
    
    def resolve_total_price(self, info):
        return sum(item.quantity * item.offer.selling_price for item in self.items.all())

class CartItemType(DjangoObjectType):
    class Meta:
        model = CartItem
        fields = "__all__"
    
    total_price = graphene.Float()
    
    def resolve_total_price(self, info):
        return self.quantity * self.offer.selling_price

class UserProfileType(DjangoObjectType):
    class Meta:
        model = UserProfile
        fields = "__all__"

class ProductExistsResponse(graphene.ObjectType):
    exists = graphene.Boolean()
    product = graphene.Field(Product)
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
    price = graphene.String()
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

# Query Class
class Query(graphene.ObjectType):
    # Product queries
    product = graphene.Field(Product, id=graphene.ID(), part_number=graphene.String())
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
        Product,
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
    
    # Add this new field
    products_search = graphene.Field(
        'ecommerce_platform.schema.RelayStyleProductConnection',
        term=graphene.String(),
        part_number=graphene.String(),
        max_price=graphene.String()
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
        if id:
            return ProductModel.objects.get(pk=id)
        if part_number:
            return ProductModel.objects.get(part_number=part_number)
        return None
    
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
            return Category.objects.filter(parent_id=parent_id)
        return Category.objects.filter(parent__isnull=True)
    
    def resolve_category(self, info, id):
        return Category.objects.get(pk=id)
    
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
                    from django_q.tasks import async_task
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

    def resolve_products_search(self, info, term=None, part_number=None, max_price=None):
        products = ProductModel.objects.all()
        
        # Apply filters
        if part_number:
            products = products.filter(part_number__icontains=part_number)
        elif term:
            products = products.filter(
                Q(name__icontains=term) | 
                Q(description__icontains=term) |
                Q(part_number__icontains=term)
            )
        
        # Type conversion is no longer needed since we're expecting a Float
        if max_price is not None:
            products = products.filter(offers__selling_price__lte=max_price)
        
        # Create edges with nodes
        edges = []
        for product in products[:50]:  # Limit to 50 items
            edge = ProductEdge(
                node=product,
                cursor=f"cursor-{product.id}"  # Simple cursor implementation
            )
            edges.append(edge)
        
        # Create page info
        has_next = products.count() > 50
        page_info = PageInfo(
            hasNextPage=has_next,
            hasPreviousPage=False,  # First page
            startCursor=edges[0].cursor if edges else "",
            endCursor=edges[-1].cursor if edges else ""
        )
        
        return RelayStyleProductConnection(
            edges=edges,
            pageInfo=page_info
        )

    def resolve_search_by_asin(self, info, asin, limit=10):
        """
        Find products that have affiliate links with the specified Amazon ASIN
        """
        logger.error(f"Searching for products with ASIN: {asin}")
        
        # Find affiliate links with the provided ASIN
        direct_match_links = AffiliateLinkModel.objects.filter(
            platform='amazon',
            platform_id=asin
        )
        
        logger.error(f"Direct match query found {direct_match_links.count()} links for ASIN={asin}")
        
        # If no direct matches, try with flexible matching
        if direct_match_links.count() == 0:
            cleaned_asin = asin.strip().upper()
            logger.error(f"Trying flexible matching with cleaned ASIN: {cleaned_asin}")
            
            direct_match_links = AffiliateLinkModel.objects.filter(
                platform='amazon'
            ).filter(
                models.Q(platform_id__iexact=asin) |
                models.Q(platform_id__iexact=cleaned_asin) |
                models.Q(platform_id__contains=cleaned_asin) |
                models.Q(original_url__contains=cleaned_asin)
            )
            
            logger.error(f"Flexible match found {direct_match_links.count()} links")
        
        # Collect product data
        results = []
        seen_product_ids = set()
        
        for link in direct_match_links:
            try:
                product = link.product
                logger.error(f"Processing product: ID={product.id}, Name={product.name}")
                
                if product.id in seen_product_ids:
                    logger.error(f"Skipping duplicate product ID: {product.id}")
                    continue
                    
                seen_product_ids.add(product.id)
                
                # Get ALL affiliate links for this product
                product_links = list(AffiliateLinkModel.objects.filter(product=product))
                logger.error(f"Found {len(product_links)} affiliate links for product {product.id}")
                
                # Get ALL offers for this product
                product_offers = list(OfferModel.objects.filter(product=product).select_related('vendor'))
                logger.error(f"Found {len(product_offers)} offers for product {product.id}")
                
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
                logger.error(f"Created ProductSearchResult for {product.id} with name={result.name}, part_number={result.part_number}")
                
                results.append(result)
                logger.error(f"Added complete product to results: {product.id}")
                
                if len(results) >= limit:
                    break
                    
            except Exception as e:
                logger.error(f"Error processing link ID={link.id}: {str(e)}")
        
        # Log what we found
        logger.error(f"Returning {len(results)} complete results for ASIN: {asin}")
        
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
            # Get all affiliate links for this product
            product_links = list(AffiliateLinkModel.objects.filter(product=product))
            
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
            # Get all affiliate links for this product
            product_links = list(AffiliateLinkModel.objects.filter(product=product))
            
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
        import json
        import redis
        import logging
        from django.conf import settings
        
        logger = logging.getLogger('affiliate_tasks')
        logger.info(f"Checking standalone affiliate URL for task_id: {task_id}")
        
        try:
            # Redis connection with proper fallbacks
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
    
    product = graphene.Field(Product)
    
    @staticmethod
    def mutate(root, info, input):
        manufacturer = ManufacturerModel.objects.get(pk=input.manufacturer_id)
        
        # Create the product
        product = ProductModel(
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
                category = Category.objects.get(pk=category_id)
                product.categories.add(category)
        
        return CreateProduct(product=product)

class UpdateProduct(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        input = ProductInput(required=True)
    
    product = graphene.Field(Product)
    
    @staticmethod
    def mutate(root, info, id, input):
        try:
            product = ProductModel.objects.get(pk=id)
        except ProductModel.DoesNotExist:
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
                category = Category.objects.get(pk=category_id)
                product.categories.add(category)
        
        return UpdateProduct(product=product)

class CreateProductFromAmazon(graphene.Mutation):
    class Arguments:
        input = AmazonProductInput(required=True)
    
    product = graphene.Field(Product)
    
    @staticmethod
    def mutate(root, info, input):
        # Get or create manufacturer
        manufacturer, created = ManufacturerModel.objects.get_or_create(
            name=input.manufacturer_name,
            defaults={'slug': input.manufacturer_name.lower().replace(' ', '-')}
        )
        
        # Create new product
        product = ProductModel(
            name=input.name,
            description=input.description,
            manufacturer=manufacturer,
            part_number=input.part_number,
            slug=input.part_number.lower().replace(' ', '-'),
            main_image=input.image,
            status='active'
        )
        product.save()
        
        # Add to category if provided
        if input.category_name:
            category, created = Category.objects.get_or_create(
                name=input.category_name,
                defaults={
                    'slug': input.category_name.lower().replace(' ', '-'),
                    'is_visible': True
                }
            )
            product.categories.add(category)
        
        # Create affiliate link for Amazon
        if input.asin and input.url:
            affiliate_link = AffiliateLinkModel(
                product=product,
                platform='amazon',
                platform_id=input.asin,
                original_url=input.url,
                affiliate_url='',  # Will be populated by background task
                is_active=True
            )
            affiliate_link.save()
            
            # Async task to generate actual affiliate URL
            from django_q.tasks import async_task
            async_task('affiliates.tasks.generate_amazon_affiliate_url', 
                      affiliate_link.id, input.asin)
        
        return CreateProductFromAmazon(product=product)

class CreateAffiliateLink(graphene.Mutation):
    class Arguments:
        input = AffiliateLinkInput(required=True)
    
    affiliate_link = graphene.Field(AffiliateLinkType)
    
    @staticmethod
    def mutate(root, info, input):
        try:
            product = ProductModel.objects.get(pk=input.product_id)
            
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
        except ProductModel.DoesNotExist:
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
                task_id, success = generate_standalone_amazon_affiliate_url(asin, url)
                
                if not success:
                    return CreateAmazonAffiliateLink(
                        taskId=None,
                        affiliateUrl=None,
                        status="error",
                        message="Failed to queue task with puppeteer service"
                    )
                
                logger.info(f"Created task ID: {task_id}")
                
                # Store product data in Redis
                redis_kwargs = get_redis_kwargs()
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
                task_id, success = generate_standalone_amazon_affiliate_url(asin, url)
                
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
    totalCount = graphene.Int()
    items = graphene.List(Product)

# Add this new class to support Relay-style connections
class ProductEdge(graphene.ObjectType):
    node = graphene.Field(Product)
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
    manufacturer = graphene.Field(Manufacturer)
    affiliate_links = graphene.List(AffiliateLinkType)
    offers = graphene.List(OfferType)
    
    # Add any other fields that your client needs

def get_redis_kwargs():
    """Helper to get standardized Redis connection kwargs"""
    redis_kwargs = {
        'host': getattr(settings, 'REDIS_HOST', 'localhost'),
        'port': getattr(settings, 'REDIS_PORT', 6379),
        'decode_responses': True
    }
    
    # Only add password if it exists in settings
    if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
        redis_kwargs['password'] = settings.REDIS_PASSWORD
        
    return redis_kwargs

schema = graphene.Schema(query=Query, mutation=Mutation)