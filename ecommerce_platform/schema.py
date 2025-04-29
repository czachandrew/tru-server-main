import graphene
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from graphql import GraphQLError
from django.db.models import Q
from django.contrib.auth.models import User

from products.models import Product as ProductModel, Category, Manufacturer
from offers.models import Offer
from vendors.models import Vendor
from affiliates.models import AffiliateLink
from store.models import Cart, CartItem, UserProfile
from ecommerce_platform.graphql.types.product import Product

# Custom Scalars
from graphene.types.scalars import Scalar
from graphene.types.datetime import DateTime
import json

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
        model = Manufacturer
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
        model = AffiliateLink
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

class UserType(DjangoObjectType):
    class Meta:
        model = User
        fields = ["id", "username", "email"]

class UserProfileType(DjangoObjectType):
    class Meta:
        model = UserProfile
        fields = "__all__"

class ProductExistsResponse(graphene.ObjectType):
    exists = graphene.Boolean()
    product = graphene.Field(Product)
    message = graphene.String()

# Input Types
class ProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    description = graphene.String()
    manufacturer_id = graphene.ID(required=True)
    part_number = graphene.String(required=True)
    category_ids = graphene.List(graphene.ID)
    specifications = JSONScalar()
    weight = graphene.Float()
    dimensions = JSONScalar()
    main_image = graphene.String()
    additional_images = graphene.List(graphene.String)
    status = graphene.String()

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
        return Manufacturer.objects.all()
    
    def resolve_manufacturer(self, info, id):
        return Manufacturer.objects.get(pk=id)
    
    def resolve_offers_by_product(self, info, product_id):
        return Offer.objects.filter(product_id=product_id)
    
    def resolve_product_exists(self, info, part_number, asin=None, url=None):
        try:
            product = ProductModel.objects.get(part_number=part_number)
            return ProductExistsResponse(
                exists=True,
                product=product,
                message="Product found in database"
            )
        except ProductModel.DoesNotExist:
            return ProductExistsResponse(
                exists=False,
                product=None,
                message="Product not found in database"
            )
    
    def resolve_affiliate_links(self, info, product_id):
        return AffiliateLink.objects.filter(product_id=product_id)
    
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

# Mutation Class
class CreateProduct(graphene.Mutation):
    class Arguments:
        input = ProductInput(required=True)
    
    product = graphene.Field(Product)
    
    @staticmethod
    def mutate(root, info, input):
        manufacturer = Manufacturer.objects.get(pk=input.manufacturer_id)
        
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
            product.manufacturer = Manufacturer.objects.get(pk=input.manufacturer_id)
        
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
        manufacturer, created = Manufacturer.objects.get_or_create(
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
            affiliate_link = AffiliateLink(
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
        product = ProductModel.objects.get(pk=input.product_id)
        
        affiliate_link = AffiliateLink(
            product=product,
            platform=input.platform,
            platform_id=input.platform_id,
            original_url=input.original_url,
            affiliate_url='',  # Will be populated later
            is_active=True
        )
        affiliate_link.save()
        
        return CreateAffiliateLink(affiliate_link=affiliate_link)

class CreateAmazonAffiliateLink(graphene.Mutation):
    class Arguments:
        asin = graphene.String(required=True)
        product_id = graphene.ID()
    
    affiliate_link = graphene.Field(AffiliateLinkType)
    
    @staticmethod
    def mutate(root, info, asin, product_id=None):
        # If product_id is not provided, check if product exists with this ASIN
        if not product_id:
            try:
                existing_link = AffiliateLink.objects.get(
                    platform='amazon',
                    platform_id=asin
                )
                return CreateAmazonAffiliateLink(affiliate_link=existing_link)
            except AffiliateLink.DoesNotExist:
                raise GraphQLError("No product found for this ASIN. Please create product first.")
        
        product = ProductModel.objects.get(pk=product_id)
        
        # Create basic affiliate link
        affiliate_link = AffiliateLink(
            product=product,
            platform='amazon',
            platform_id=asin,
            original_url=f"https://www.amazon.com/dp/{asin}",
            affiliate_url='',  # Will be populated by background task
            is_active=True
        )
        affiliate_link.save()
        
        # Queue background task to generate actual affiliate URL
        from django_q.tasks import async_task
        async_task('affiliates.tasks.generate_amazon_affiliate_url', 
                  affiliate_link.id, asin)
        
        return CreateAmazonAffiliateLink(affiliate_link=affiliate_link)

class UpdateAffiliateLink(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        is_active = graphene.Boolean()
    
    affiliate_link = graphene.Field(AffiliateLinkType)
    
    @staticmethod
    def mutate(root, info, id, is_active=None):
        affiliate_link = AffiliateLink.objects.get(pk=id)
        
        if is_active is not None:
            affiliate_link.is_active = is_active
            
        affiliate_link.save()
        
        return UpdateAffiliateLink(affiliate_link=affiliate_link)

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
        offer = Offer.objects.get(pk=item.offer_id)
        
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

class Mutation(graphene.ObjectType):
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

schema = graphene.Schema(query=Query, mutation=Mutation)