import graphene
from graphene_django import DjangoObjectType
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
    
    # GraphQL expects camelCase but Django uses snake_case
    mainImage = graphene.String(source='main_image')
    additionalImages = graphene.List(graphene.String, source='additional_images')
    partNumber = graphene.String(source='part_number')
    dimensions = graphene.Field('ecommerce_platform.schema.Dimensions')
    
    def resolve_dimensions(self, info):
        return self.dimensions or {}

class CategoryType(DjangoObjectType):
    class Meta:
        model = CategoryModel
        fields = "__all__"

class ManufacturerType(DjangoObjectType):
    class Meta:
        model = ManufacturerModel
        fields = "__all__"

