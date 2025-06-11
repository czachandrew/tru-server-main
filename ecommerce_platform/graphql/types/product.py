import graphene
from graphene_django import DjangoObjectType
from graphene import relay
from products.models import Product as ProductModel, Category as CategoryModel, Manufacturer as ManufacturerModel

class Product(DjangoObjectType):
    exists = graphene.Boolean(default_value=True)
    
    class Meta:
        model = ProductModel
        name = "Product"
        fields = (
            "id", "name", "slug", "description", "specifications", 
            "manufacturer", "part_number", "categories", "weight", 
            "dimensions", "main_image", "additional_images",
            "status", "created_at", "updated_at", "offers",
            "affiliate_links"
        )

class ProductType(DjangoObjectType):
    class Meta:
        model = ProductModel
        fields = "__all__"
        name = "Product"
        interfaces = (relay.Node, )  # This enables the connection
        filter_fields = {
            'name': ['exact', 'icontains', 'istartswith'],
            'part_number': ['exact', 'icontains'],
            # add other fields as needed
        }
        connection_class = relay.Connection
    
    # GraphQL expects camelCase but Django uses snake_case
    mainImage = graphene.String(source='main_image')
    additionalImages = graphene.List(graphene.String, source='additional_images')
    partNumber = graphene.String(source='part_number')
    dimensions = graphene.Field('ecommerce_platform.schema.Dimensions')
    
    # BACKWARD COMPATIBILITY: Chrome extension expects asin field
    asin = graphene.String()
    
    def resolve_dimensions(self, info):
        return self.dimensions or {}
    
    def resolve_asin(self, info):
        """
        Resolve ASIN from affiliate links if available
        Chrome extension expects this field for Amazon compatibility
        """
        # Check if product has Amazon affiliate link
        from affiliates.models import AffiliateLink
        amazon_link = AffiliateLink.objects.filter(
            product=self,
            platform='amazon'
        ).first()
        
        if amazon_link:
            return amazon_link.platform_id
        
        # Fallback: check if part_number looks like an ASIN (10 chars, alphanumeric)
        if self.part_number and len(self.part_number) == 10 and self.part_number.isalnum():
            return self.part_number
            
        return None

class CategoryType(DjangoObjectType):
    class Meta:
        model = CategoryModel
        fields = "__all__"

class ManufacturerType(DjangoObjectType):
    class Meta:
        model = ManufacturerModel
        fields = "__all__"

