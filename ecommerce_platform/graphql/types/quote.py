import graphene
from graphene_django import DjangoObjectType
from graphene import relay
from quotes.models import Quote, QuoteItem, ProductMatch, VendorPricing

class QuoteType(DjangoObjectType):
    """GraphQL type for Quote model"""
    
    item_count = graphene.Int()
    matched_item_count = graphene.Int()
    potential_savings = graphene.Decimal()
    affiliate_opportunities = graphene.Int()
    estimated_time_remaining = graphene.Int()
    
    class Meta:
        model = Quote
        fields = (
            'id', 'user', 'vendor_name', 'vendor_company', 'quote_number', 
            'quote_date', 'pdf_file', 'original_filename', 'subtotal', 
            'tax', 'shipping', 'total', 'status', 'demo_mode_enabled',
            'parsing_error', 'created_at', 'updated_at', 'processed_at', 'items'
        )
    
    def resolve_item_count(self, info):
        return self.item_count
    
    def resolve_matched_item_count(self, info):
        return self.matched_item_count
    
    def resolve_potential_savings(self, info):
        """Calculate total potential savings from all matched items"""
        from decimal import Decimal
        total_savings = Decimal('0.00')
        
        for item in self.items.all():
            # Get the best match for this item (most negative price difference = biggest savings)
            best_match = item.matches.filter(
                price_difference__lt=0  # Negative means we found a better price
            ).order_by('price_difference').first()
            
            if best_match:
                # price_difference is negative for savings, so we need to make it positive
                item_savings = abs(best_match.price_difference) * item.quantity
                total_savings += item_savings
        
        return total_savings
    
    def resolve_affiliate_opportunities(self, info):
        """Count items that have affiliate link alternatives"""
        affiliate_count = 0
        
        for item in self.items.all():
            # Check if any matches have products with affiliate links
            for match in item.matches.all():
                if match.product and match.product.affiliate_links.filter(is_active=True).exists():
                    affiliate_count += 1
                    break  # Count each item only once
        
        return affiliate_count
    
    def resolve_estimated_time_remaining(self, info):
        """Calculate estimated time remaining for processing"""
        if self.status in ['completed', 'error']:
            return None
        
        from django.utils import timezone
        
        # Base estimates for each status
        step_estimates = {
            'uploading': 5,
            'parsing': 25, 
            'matching': 15
        }
        
        if self.status not in step_estimates:
            return None
        
        processing_time = (timezone.now() - self.created_at).total_seconds()
        base_estimate = step_estimates[self.status]
        
        # Adjust estimates based on processing time and quote characteristics
        if self.status == 'parsing':
            # If parsing is taking longer, increase estimate
            if processing_time > 10:
                base_estimate = max(base_estimate, int(processing_time * 1.2))
        elif self.status == 'matching':
            # Estimate based on number of items
            total_items = self.items.count()
            if total_items > 0:
                base_estimate = min(30, max(10, total_items * 2))  # 2 seconds per item, max 30s
        
        estimated_remaining = max(5, base_estimate - int(processing_time))
        return estimated_remaining

class QuoteItemType(DjangoObjectType):
    """GraphQL type for QuoteItem model"""
    
    best_match = graphene.Field('ecommerce_platform.graphql.types.quote.ProductMatchType')
    has_exact_match = graphene.Boolean()
    
    class Meta:
        model = QuoteItem
        fields = (
            'id', 'quote', 'line_number', 'part_number', 'description', 
            'manufacturer', 'quantity', 'unit_price', 'total_price', 
            'vendor_sku', 'notes', 'is_quote_price', 'price_confidence',
            'extraction_confidence', 'created_at', 'updated_at', 'matches'
        )
    
    def resolve_best_match(self, info):
        return self.best_match
    
    def resolve_has_exact_match(self, info):
        return self.has_exact_match

class ProductMatchType(DjangoObjectType):
    """GraphQL type for ProductMatch model"""
    
    is_better_price = graphene.Boolean()
    
    class Meta:
        model = ProductMatch
        fields = (
            'id', 'quote_item', 'product', 'confidence', 'is_exact_match',
            'match_method', 'price_difference', 'price_difference_percentage',
            'is_demo_price', 'demo_generated_product', 'suggested_product',
            'created_at', 'updated_at'
        )
    
    def resolve_is_better_price(self, info):
        return self.is_better_price

class VendorPricingType(DjangoObjectType):
    """GraphQL type for VendorPricing model"""
    
    class Meta:
        model = VendorPricing
        fields = (
            'id', 'product', 'vendor_company', 'vendor_name', 'quoted_price',
            'quantity', 'quote_date', 'source_quote', 'source_quote_item',
            'is_confirmed', 'confirmation_date', 'part_number_used', 'notes',
            'created_at', 'updated_at'
        )

# Enums for GraphQL
class QuoteStatusEnum(graphene.Enum):
    UPLOADING = 'uploading'
    PARSING = 'parsing'
    MATCHING = 'matching'
    COMPLETED = 'completed'
    ERROR = 'error'

class MatchMethodEnum(graphene.Enum):
    EXACT_PART_NUMBER = 'exact_part_number'
    FUZZY_PART_NUMBER = 'fuzzy_part_number'
    MANUFACTURER_MATCH = 'manufacturer_match'
    DESCRIPTION_SIMILARITY = 'description_similarity'
    DEMO_GENERATED = 'demo_generated'
    MANUAL = 'manual'

# Connection types for pagination
class QuoteConnection(relay.Connection):
    class Meta:
        node = QuoteType

class QuoteItemConnection(relay.Connection):
    class Meta:
        node = QuoteItemType

class ProductMatchConnection(relay.Connection):
    class Meta:
        node = ProductMatchType

# Response types for mutations
class QuoteUploadResponse(graphene.ObjectType):
    success = graphene.Boolean()
    message = graphene.String()
    quote = graphene.Field(QuoteType)
    errors = graphene.List(graphene.String)

class QuoteMatchResponse(graphene.ObjectType):
    success = graphene.Boolean()
    message = graphene.String()
    quote = graphene.Field(QuoteType)
    matched_items = graphene.Int()
    total_items = graphene.Int()
    errors = graphene.List(graphene.String)

class QuoteProcessingStatus(graphene.ObjectType):
    quote_id = graphene.ID()
    status = graphene.Field(QuoteStatusEnum)
    progress_percentage = graphene.Int()
    current_step = graphene.String()
    error_message = graphene.String()
    items_processed = graphene.Int()
    total_items = graphene.Int()
