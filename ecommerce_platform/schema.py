import graphene
from graphene_django import DjangoObjectType
from products.models import Product, Category, Manufacturer
from offers.models import Offer
from affiliates.models import AffiliateLink

class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = "__all__"

class CategoryType(DjangoObjectType):
    class Meta:
        model = Category
        fields = "__all__"

class ManufacturerType(DjangoObjectType):
    class Meta:
        model = Manufacturer
        fields = "__all__"

class OfferType(DjangoObjectType):
    class Meta:
        model = Offer
        fields = "__all__"

class AffiliateLinkType(DjangoObjectType):
    class Meta:
        model = AffiliateLink
        fields = "__all__"

class Query(graphene.ObjectType):
    # Product queries
    product = graphene.Field(ProductType, id=graphene.ID(), part_number=graphene.String())
    products = graphene.List(ProductType, 
                            search=graphene.String(),
                            category_id=graphene.ID(),
                            manufacturer_id=graphene.ID())
    
    # Category queries
    categories = graphene.List(CategoryType, parent_id=graphene.ID())
    
    # Offer queries
    offers_by_product = graphene.List(OfferType, product_id=graphene.ID(required=True))
    
    # Affiliate links
    affiliate_links = graphene.List(AffiliateLinkType, product_id=graphene.ID(required=True))
    
    def resolve_product(self, info, id=None, part_number=None):
        if id:
            return Product.objects.get(pk=id)
        if part_number:
            return Product.objects.get(part_number=part_number)
        return None
    
    def resolve_products(self, info, search=None, category_id=None, manufacturer_id=None):
        products = Product.objects.all()
        
        if search:
            products = products.filter(search_vector=search)
        if category_id:
            products = products.filter(categories__id=category_id)
        if manufacturer_id:
            products = products.filter(manufacturer_id=manufacturer_id)
            
        return products
    
    def resolve_categories(self, info, parent_id=None):
        if parent_id:
            return Category.objects.filter(parent_id=parent_id)
        return Category.objects.filter(parent__isnull=True)
    
    def resolve_offers_by_product(self, info, product_id):
        return Offer.objects.filter(product_id=product_id)
    
    def resolve_affiliate_links(self, info, product_id):
        return AffiliateLink.objects.filter(product_id=product_id)

schema = graphene.Schema(query=Query)

