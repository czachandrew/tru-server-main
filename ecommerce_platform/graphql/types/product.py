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

class Category(DjangoObjectType):
    class Meta:
        model = CategoryModel
        name = "Category"
        fields = (
            "id", "name", "slug", "description", "parent", 
            "image", "display_order", "is_visible", "children"
        )

class Manufacturer(DjangoObjectType):
    class Meta:
        model = ManufacturerModel
        name = "Manufacturer"
        fields = (
            "id", "name", "slug", "logo", "website", 
            "description", "products"
        ) 