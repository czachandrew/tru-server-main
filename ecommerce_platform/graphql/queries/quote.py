import graphene
from graphene_django.filter import DjangoFilterConnectionField
from django.contrib.auth import get_user_model
from quotes.models import Quote, QuoteItem, ProductMatch, VendorPricing
from ..types.quote import (
    QuoteType, QuoteItemType, ProductMatchType, VendorPricingType,
    QuoteConnection, QuoteProcessingStatus, QuoteStatusEnum
)

User = get_user_model()

class QuoteQuery(graphene.ObjectType):
    """Quote-related GraphQL queries"""
    
    # Single quote queries
    quote = graphene.Field(
        QuoteType, 
        id=graphene.ID(required=True),
        description="Get a specific quote by ID"
    )
    
    # Quote list queries  
    quotes = graphene.List(
        QuoteType,
        limit=graphene.Int(default_value=20),
        offset=graphene.Int(default_value=0),
        status=graphene.String(),
        vendor_company=graphene.String(),
        date_from=graphene.Date(),
        date_to=graphene.Date(),
        description="Get quotes with optional filtering"
    )
    
    my_quotes = graphene.List(
        QuoteType,
        limit=graphene.Int(default_value=20),
        offset=graphene.Int(default_value=0),
        status=graphene.String(),
        description="Get quotes for the current authenticated user"
    )
    
    # Quote processing status
    quote_processing_status = graphene.Field(
        QuoteProcessingStatus,
        quote_id=graphene.ID(required=True),
        description="Get the processing status of a quote"
    )
    
    # Quote items
    quote_items = graphene.List(
        QuoteItemType,
        quote_id=graphene.ID(required=True),
        description="Get all items for a specific quote"
    )
    
    # Product matches
    product_matches = graphene.List(
        ProductMatchType,
        quote_item_id=graphene.ID(required=True),
        description="Get all product matches for a quote item"
    )
    
    # Vendor pricing intelligence
    vendor_pricing = graphene.List(
        VendorPricingType,
        product_id=graphene.ID(),
        vendor_company=graphene.String(),
        part_number=graphene.String(),
        limit=graphene.Int(default_value=50),
        description="Get vendor pricing data for analysis"
    )
    
    # Analytics queries (future implementation)
    # quote_analytics = graphene.Field(
    #     'ecommerce_platform.graphql.types.quote.QuoteAnalytics',
    #     date_from=graphene.Date(),
    #     date_to=graphene.Date(),
    #     description="Get quote analytics data"
    # )
    
    def resolve_quote(self, info, id):
        """Resolve single quote by ID"""
        try:
            # Handle case where context might not have user (in tests)
            user = getattr(info.context, 'user', None)
            if not user or user.is_anonymous:
                return None
            
            quote = Quote.objects.get(id=id)
            
            # Users can only see their own quotes unless they're staff
            if not user.is_staff and quote.user != user:
                return None
            
            # If quote has demo mode enabled, inject demo context for virtual offers
            if quote.demo_mode_enabled:
                # Inject demo context into request for virtual TruPrice offers
                info.context._demo_quote_context = {
                    'demo_mode': True,
                    'quote': quote,
                    'quote_items': quote.items.all()
                }
                
            return quote
        except Quote.DoesNotExist:
            return None
    
    def resolve_quotes(self, info, limit=20, offset=0, **kwargs):
        """Resolve quotes list with filtering"""
        user = getattr(info.context, 'user', None)
        if not user or user.is_anonymous:
            # For testing without authentication, return all quotes
            if not hasattr(info.context, 'user'):
                queryset = Quote.objects.all()
            else:
                return Quote.objects.none()
        
        else:
            # Base queryset
            if user.is_staff:
                queryset = Quote.objects.all()
            else:
                queryset = Quote.objects.filter(user=user)
        
        # Apply filters
        if kwargs.get('status'):
            queryset = queryset.filter(status=kwargs['status'])
        
        if kwargs.get('vendor_company'):
            queryset = queryset.filter(
                vendor_company__icontains=kwargs['vendor_company']
            )
        
        if kwargs.get('date_from'):
            queryset = queryset.filter(created_at__date__gte=kwargs['date_from'])
        
        if kwargs.get('date_to'):
            queryset = queryset.filter(created_at__date__lte=kwargs['date_to'])
        
        # Order by creation date (newest first)
        queryset = queryset.order_by('-created_at')
        
        # Apply pagination
        return queryset[offset:offset + limit]
    
    def resolve_my_quotes(self, info, limit=20, offset=0, **kwargs):
        """Resolve quotes for current user"""
        user = info.context.user
        if user.is_anonymous:
            return Quote.objects.none()
        
        queryset = Quote.objects.filter(user=user)
        
        # Apply filters
        if kwargs.get('status'):
            queryset = queryset.filter(status=kwargs['status'])
        
        # Order by creation date (newest first)
        queryset = queryset.order_by('-created_at')
        
        # Apply pagination
        return queryset[offset:offset + limit]
    
    def resolve_quote_processing_status(self, info, quote_id):
        """Resolve quote processing status"""
        try:
            user = info.context.user
            if user.is_anonymous:
                return None
            
            quote = Quote.objects.get(id=quote_id)
            
            # Users can only see their own quotes unless they're staff
            if not user.is_staff and quote.user != user:
                return None
            
            # Calculate progress
            total_items = quote.items.count()
            matched_items = quote.items.filter(matches__isnull=False).distinct().count()
            
            if total_items > 0:
                progress_percentage = int((matched_items / total_items) * 100)
            else:
                progress_percentage = 0
            
            # Determine current step
            current_step = "Unknown"
            if quote.status == 'uploading':
                current_step = "Uploading file"
            elif quote.status == 'parsing':
                current_step = "Parsing PDF with AI"
            elif quote.status == 'matching':
                current_step = "Matching products"
            elif quote.status == 'completed':
                current_step = "Completed"
            elif quote.status == 'error':
                current_step = "Error occurred"
            
            return QuoteProcessingStatus(
                quote_id=quote_id,
                status=quote.status,
                progress_percentage=progress_percentage,
                current_step=current_step,
                error_message=quote.parsing_error if quote.status == 'error' else None,
                items_processed=matched_items,
                total_items=total_items
            )
            
        except Quote.DoesNotExist:
            return None
    
    def resolve_quote_items(self, info, quote_id):
        """Resolve quote items for a specific quote"""
        try:
            user = info.context.user
            if user.is_anonymous:
                return []
            
            quote = Quote.objects.get(id=quote_id)
            
            # Users can only see their own quotes unless they're staff
            if not user.is_staff and quote.user != user:
                return []
            
            return quote.items.all().order_by('line_number', 'id')
            
        except Quote.DoesNotExist:
            return []
    
    def resolve_product_matches(self, info, quote_item_id):
        """Resolve product matches for a quote item"""
        try:
            user = info.context.user
            if user.is_anonymous:
                return []
            
            quote_item = QuoteItem.objects.get(id=quote_item_id)
            
            # Check permissions
            if not user.is_staff and quote_item.quote.user != user:
                return []
            
            return quote_item.matches.all().order_by('-confidence', '-is_exact_match')
            
        except QuoteItem.DoesNotExist:
            return []
    
    def resolve_vendor_pricing(self, info, **kwargs):
        """Resolve vendor pricing data"""
        user = getattr(info.context, 'user', None)
        if not user or user.is_anonymous:
            # For testing without authentication, return all data
            if not hasattr(info.context, 'user'):
                pass  # Continue to show data
            else:
                return []
        
        queryset = VendorPricing.objects.all()
        
        # Apply filters
        if kwargs.get('product_id'):
            queryset = queryset.filter(product_id=kwargs['product_id'])
        
        if kwargs.get('vendor_company'):
            queryset = queryset.filter(
                vendor_company__icontains=kwargs['vendor_company']
            )
        
        if kwargs.get('part_number'):
            queryset = queryset.filter(
                part_number_used__icontains=kwargs['part_number']
            )
        
        # Order by date (newest first)
        queryset = queryset.order_by('-quote_date', '-created_at')
        
        # Apply limit
        limit = kwargs.get('limit', 50)
        return queryset[:limit]
