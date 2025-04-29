import graphene
from graphene_django import DjangoObjectType
from offers.models import Offer as OfferModel
from vendors.models import Vendor as VendorModel

class Offer(DjangoObjectType):
    class Meta:
        model = OfferModel
        name = "Offer"
        fields = (
            "id", "product", "vendor", "cost_price", "selling_price",
            "msrp", "vendor_sku", "vendor_url", "stock_quantity",
            "is_in_stock", "availability_updated_at", "created_at", "updated_at"
        )
        # Note: You might want to exclude cost_price in production
        # as it could be sensitive business information

class Vendor(DjangoObjectType):
    class Meta:
        model = VendorModel
        name = "Vendor"
        fields = (
            "id", "name", "code", "contact_name", "contact_email",
            "contact_phone", "api_endpoint", "payment_terms",
            "shipping_terms", "is_active", "offers"
        )
        # Remove the exclude line - can't use both fields and exclude
        # exclude = ("api_credentials",) 