import graphene
from graphene_django import DjangoObjectType
from offers.models import Offer
from vendors.models import Vendor

class OfferType(DjangoObjectType):
    # Add enhanced product information fields for frontend display
    product_name = graphene.String()
    product_part_number = graphene.String()
    product_image = graphene.String()
    product_description = graphene.String()
    product_manufacturer = graphene.String()
    
    class Meta:
        model = Offer
        fields = "__all__"
    
    def resolve_product_name(self, info):
        """Return the actual product name for this offer"""
        return self.product.name if self.product else None
    
    def resolve_product_part_number(self, info):
        """Return the actual product part number for this offer"""
        return self.product.part_number if self.product else None
    
    def resolve_product_image(self, info):
        """Return the actual product image for this offer"""
        return self.product.main_image if self.product else None
    
    def resolve_product_description(self, info):
        """Return the actual product description for this offer"""
        return self.product.description if self.product else None
    
    def resolve_product_manufacturer(self, info):
        """Return the actual manufacturer name for this offer"""
        return self.product.manufacturer.name if (self.product and self.product.manufacturer) else None

class VendorType(DjangoObjectType):
    class Meta:
        model = Vendor
        fields = "__all__"

class Offer(DjangoObjectType):
    # Add the same enhanced fields for consistency
    product_name = graphene.String()
    product_part_number = graphene.String()
    product_image = graphene.String()
    product_description = graphene.String()
    product_manufacturer = graphene.String()
    
    class Meta:
        model = Offer
        name = "Offer"
        fields = (
            "id", "product", "vendor", "cost_price", "selling_price",
            "msrp", "vendor_sku", "vendor_url", "stock_quantity",
            "is_in_stock", "availability_updated_at", "created_at", "updated_at"
        )
        # Note: You might want to exclude cost_price in production
        # as it could be sensitive business information
    
    def resolve_product_name(self, info):
        return self.product.name if self.product else None
    
    def resolve_product_part_number(self, info):
        return self.product.part_number if self.product else None
    
    def resolve_product_image(self, info):
        return self.product.main_image if self.product else None
    
    def resolve_product_description(self, info):
        return self.product.description if self.product else None
    
    def resolve_product_manufacturer(self, info):
        return self.product.manufacturer.name if (self.product and self.product.manufacturer) else None

class Vendor(DjangoObjectType):
    class Meta:
        model = Vendor
        name = "Vendor"
        fields = (
            "id", "name", "code", "contact_name", "contact_email",
            "contact_phone", "api_endpoint", "payment_terms",
            "shipping_terms", "is_active", "offers"
        )
        # Remove the exclude line - can't use both fields and exclude
        # exclude = ("api_credentials",) 