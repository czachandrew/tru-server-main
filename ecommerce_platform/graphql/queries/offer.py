import graphene
from offers.models import Offer
from vendors.models import Vendor
from ..types.offer import OfferType, VendorType, OfferTypeEnum, VendorTypeEnum

class OfferQuery(graphene.ObjectType):
    # HYBRID ARCHITECTURE: Enhanced queries for unified offer system
    offers_by_product = graphene.List(
        OfferType, 
        product_id=graphene.ID(required=True),
        offer_type=graphene.Argument(OfferTypeEnum),
        is_active=graphene.Boolean(default_value=True)
    )
    
    # Chrome Extension Compatibility: Add camelCase aliases
    offersByProduct = graphene.List(
        OfferType, 
        productId=graphene.ID(required=True),
        offerType=graphene.Argument(OfferTypeEnum),
        isActive=graphene.Boolean(default_value=True),
        description="Chrome extension compatible offers query (camelCase)"
    )
    
    # Separate queries for different offer types
    supplier_offers = graphene.List(
        OfferType,
        product_id=graphene.ID(),
        vendor_id=graphene.ID()
    )
    
    affiliate_offers = graphene.List(
        OfferType,
        product_id=graphene.ID(),
        platform=graphene.String()
    )
    
    # Enhanced vendor queries
    vendors = graphene.List(
        VendorType,
        vendor_type=graphene.Argument(VendorTypeEnum),
        is_active=graphene.Boolean(default_value=True)
    )
    
    # Pricing intelligence queries
    best_price_offers = graphene.List(
        OfferType,
        product_id=graphene.ID(required=True),
        limit=graphene.Int(default_value=5)
    )
    
    price_comparison = graphene.List(
        OfferType,
        product_id=graphene.ID(required=True),
        include_affiliate=graphene.Boolean(default_value=True),
        include_supplier=graphene.Boolean(default_value=True)
    )
    
    # Chrome Extension Compatibility: Add camelCase alias for priceComparison
    priceComparison = graphene.List(
        OfferType,
        productId=graphene.ID(required=True),
        includeAffiliate=graphene.Boolean(default_value=True),
        includeSupplier=graphene.Boolean(default_value=True),
        description="Chrome extension compatible price comparison query (camelCase)"
    )
    
    def resolve_offers_by_product(self, info, product_id, offer_type=None, is_active=True):
        """Get all offers for a product with optional filtering"""
        queryset = Offer.objects.filter(product_id=product_id)
        
        if is_active:
            queryset = queryset.filter(is_active=True)
        
        if offer_type:
            queryset = queryset.filter(offer_type=offer_type)
            
        return queryset.select_related('product', 'vendor').order_by('selling_price')
    
    def resolve_offersByProduct(self, info, productId, offerType=None, isActive=True):
        """Chrome extension compatible offers resolver (camelCase)"""
        return self.resolve_offers_by_product(info, productId, offerType, isActive)
    
    def resolve_supplier_offers(self, info, product_id=None, vendor_id=None):
        """Get supplier offers only"""
        queryset = Offer.objects.filter(offer_type='supplier', is_active=True)
        
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if vendor_id:
            queryset = queryset.filter(vendor_id=vendor_id)
            
        return queryset.select_related('product', 'vendor').order_by('selling_price')
    
    def resolve_affiliate_offers(self, info, product_id=None, platform=None):
        """Get affiliate offers only"""
        queryset = Offer.objects.filter(offer_type='affiliate', is_active=True)
        
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if platform:
            # Filter by vendor name containing platform (e.g., "Amazon Marketplace")
            queryset = queryset.filter(vendor__name__icontains=platform)
            
        return queryset.select_related('product', 'vendor').order_by('selling_price')
    
    def resolve_vendors(self, info, vendor_type=None, is_active=True):
        """Get vendors with optional filtering"""
        queryset = Vendor.objects.all()
        
        if is_active:
            queryset = queryset.filter(is_active=True)
        if vendor_type:
            queryset = queryset.filter(vendor_type=vendor_type)
            
        return queryset.prefetch_related('offers').order_by('name')
    
    def resolve_best_price_offers(self, info, product_id, limit=5):
        """Get best price offers for a product (from all sources)"""
        return Offer.objects.filter(
            product_id=product_id,
            is_active=True,
            is_in_stock=True
        ).select_related('product', 'vendor').order_by('selling_price')[:limit]
    
    def resolve_price_comparison(self, info, product_id, include_affiliate=True, include_supplier=True):
        """Get comprehensive price comparison across all offer types"""
        queryset = Offer.objects.filter(
            product_id=product_id,
            is_active=True,
            is_in_stock=True
        )
        
        # Filter by offer types based on preferences
        offer_types = []
        if include_supplier:
            offer_types.append('supplier')
        if include_affiliate:
            offer_types.append('affiliate')
        
        if offer_types:
            queryset = queryset.filter(offer_type__in=offer_types)
        
        return queryset.select_related('product', 'vendor').order_by('selling_price')
    
    def resolve_priceComparison(self, info, productId, includeAffiliate=True, includeSupplier=True):
        """Chrome extension compatible price comparison resolver (camelCase)"""
        return self.resolve_price_comparison(info, productId, includeAffiliate, includeSupplier) 