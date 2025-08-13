import graphene
from graphene_django import DjangoObjectType
from offers.models import Offer, OFFER_TYPE_CHOICES
from vendors.models import Vendor, VENDOR_TYPE_CHOICES

# GraphQL Enums for choices
class OfferTypeEnum(graphene.Enum):
    """Offer type enumeration"""
    SUPPLIER = 'supplier'
    AFFILIATE = 'affiliate'
    QUOTE = 'quote'

class VendorTypeEnum(graphene.Enum):
    """Vendor type enumeration"""
    SUPPLIER = 'supplier'
    AFFILIATE = 'affiliate'
    DISTRIBUTOR = 'distributor'
    MARKETPLACE = 'marketplace'

class OfferType(DjangoObjectType):
    """HYBRID ARCHITECTURE: Unified offer type supporting both supplier and affiliate offers"""
    
    # Add enhanced product information fields for frontend display
    product_name = graphene.String()
    product_part_number = graphene.String()
    product_image = graphene.String()
    product_description = graphene.String()
    product_manufacturer = graphene.String()
    
    # Hybrid-specific fields with proper typing
    offer_type = graphene.Field(OfferTypeEnum)
    is_affiliate = graphene.Boolean()
    is_supplier = graphene.Boolean()
    is_quote = graphene.Boolean()
    
    # Price tracking for affiliates
    price_history_length = graphene.Int()
    latest_price_change = graphene.String()
    
    # Commission calculations
    commission_amount = graphene.Decimal()
    
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
    
    def resolve_is_affiliate(self, info):
        """Quick check if this is an affiliate offer"""
        return self.offer_type == 'affiliate'
    
    def resolve_is_supplier(self, info):
        """Quick check if this is a supplier offer"""
        return self.offer_type == 'supplier'
    
    def resolve_is_quote(self, info):
        """Quick check if this is a quote-based offer"""
        return self.offer_type == 'quote'
    
    def resolve_price_history_length(self, info):
        """Return number of price history entries"""
        return len(self.price_history) if self.price_history else 0
    
    def resolve_latest_price_change(self, info):
        """Return latest price change timestamp"""
        if self.price_history and len(self.price_history) > 0:
            return self.price_history[-1].get('timestamp')
        return None
    
    def resolve_commission_amount(self, info):
        """Return calculated commission amount for affiliate offers"""
        if self.offer_type == 'affiliate' and self.commission_rate and self.selling_price:
            return (self.selling_price * self.commission_rate) / 100
        return None

class VendorType(DjangoObjectType):
    """Enhanced vendor type supporting both suppliers and affiliates"""
    
    vendor_type = graphene.Field(VendorTypeEnum)
    is_affiliate = graphene.Boolean()
    total_offers = graphene.Int()
    active_offers = graphene.Int()
    affiliate_offers = graphene.Int()
    supplier_offers = graphene.Int()
    
    class Meta:
        model = Vendor
        fields = "__all__"
    
    def resolve_total_offers(self, info):
        """Return total number of offers from this vendor"""
        return self.offers.count()
    
    def resolve_active_offers(self, info):
        """Return number of active offers from this vendor"""
        return self.offers.filter(is_active=True).count()
    
    def resolve_affiliate_offers(self, info):
        """Return number of affiliate offers from this vendor"""
        return self.offers.filter(offer_type='affiliate').count()
    
    def resolve_supplier_offers(self, info):
        """Return number of supplier offers from this vendor"""
        return self.offers.filter(offer_type='supplier').count()

# BACKWARD COMPATIBILITY: Keep old names but redirect to new types
class Offer(OfferType):
    """Backward compatibility alias"""
    class Meta:
        model = Offer
        name = "Offer"
        fields = (
            "id", "product", "vendor", "cost_price", "selling_price",
            "msrp", "vendor_sku", "vendor_url", "stock_quantity",
            "is_in_stock", "availability_updated_at", "created_at", "updated_at",
            # Hybrid fields
            "offer_type", "commission_rate", "expected_commission",
            "price_last_updated", "price_history",
            # Quote-specific fields
            "is_confirmed", "source_quote"
        )

class Vendor(VendorType):
    """Backward compatibility alias"""
    class Meta:
        model = Vendor
        name = "Vendor"
        fields = (
            "id", "name", "slug", "code", "vendor_type", "website", "description",
            "contact_name", "contact_email", "contact_phone", "api_endpoint", 
            "payment_terms", "shipping_terms", "is_affiliate", "affiliate_program",
            "default_commission_rate", "is_active", "offers"
        ) 