import graphene
from django.db.models import Q
from products.models import Product, Category, Manufacturer
from ..types import ProductType, CategoryType, ManufacturerType, ProductExistsResponse

class ProductQuery(graphene.ObjectType):
    product = graphene.Field(
        ProductType, 
        id=graphene.ID(), 
        part_number=graphene.String()
    )
    products = graphene.List(
        ProductType,
        search=graphene.String(),
        category_id=graphene.ID(),
        manufacturer_id=graphene.ID(),
        limit=graphene.Int(),
        offset=graphene.Int()
    )
    categories = graphene.List(CategoryType, parent_id=graphene.ID())
    category = graphene.Field(CategoryType, id=graphene.ID(required=True))
    manufacturers = graphene.List(ManufacturerType)
    manufacturer = graphene.Field(ManufacturerType, id=graphene.ID(required=True))
    product_exists = graphene.Field(
        ProductExistsResponse,
        part_number=graphene.String(required=True),
        asin=graphene.String(),
        url=graphene.String()
    )
    featuredProducts = graphene.List(
        ProductType,
        limit=graphene.Int()
    )
    
    def resolve_product(self, info, id=None, part_number=None):
        if id:
            return Product.objects.get(pk=id)
        if part_number:
            return Product.objects.get(part_number=part_number)
        return None
    
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
        try:
            product = Product.objects.get(part_number=part_number)
            return ProductExistsResponse(
                exists=True,
                product=product,
                message="Product found"
            )
        except Product.DoesNotExist:
            return ProductExistsResponse(
                exists=False,
                product=None,
                message="Product not found"
            )
    
    def resolve_featuredProducts(self, info, limit=None):
        """
        Resolver with prefetch optimization
        """
        queryset = Product.objects.filter(status='active', is_featured=True)
        
        if queryset.count() == 0:
            queryset = Product.objects.filter(status='active').order_by('-created_at')
        
        # Prefetch related data to avoid N+1 query issues
        queryset = queryset.prefetch_related(
            'manufacturer',
            'categories',
            'offers',
            'offers__vendor'
        )
        
        if limit:
            queryset = queryset[:limit]
        
        return queryset 