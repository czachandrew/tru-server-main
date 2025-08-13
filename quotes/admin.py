from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Quote, QuoteItem, ProductMatch, VendorPricing

@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'vendor_company', 'quote_number', 'user', 'status', 
        'total', 'item_count', 'matched_item_count', 'demo_mode_enabled', 'created_at'
    ]
    list_filter = ['status', 'demo_mode_enabled', 'created_at', 'vendor_company']
    search_fields = ['vendor_company', 'vendor_name', 'quote_number', 'user__email']
    readonly_fields = [
        'created_at', 'updated_at', 'processed_at', 'openai_task_id', 
        'raw_openai_response', 'item_count', 'matched_item_count'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'vendor_name', 'vendor_company', 'quote_number', 'quote_date')
        }),
        ('File', {
            'fields': ('pdf_file', 'original_filename')
        }),
        ('Financial Data', {
            'fields': ('subtotal', 'tax', 'shipping', 'total')
        }),
        ('Processing', {
            'fields': ('status', 'demo_mode_enabled', 'parsing_error', 'openai_task_id')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'processed_at'),
            'classes': ('collapse',)
        }),
        ('Analytics', {
            'fields': ('item_count', 'matched_item_count'),
            'classes': ('collapse',)
        }),
        ('Debug', {
            'fields': ('raw_openai_response',),
            'classes': ('collapse',)
        })
    )
    
    def item_count(self, obj):
        return obj.item_count
    item_count.short_description = 'Total Items'
    
    def matched_item_count(self, obj):
        return obj.matched_item_count
    matched_item_count.short_description = 'Matched Items'

class ProductMatchInline(admin.TabularInline):
    model = ProductMatch
    extra = 0
    readonly_fields = ['confidence', 'price_difference', 'match_method', 'created_at']
    fields = ['product', 'confidence', 'is_exact_match', 'match_method', 'price_difference', 'is_demo_price']

@admin.register(QuoteItem)
class QuoteItemAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'quote', 'part_number', 'description_truncated', 'manufacturer',
        'quantity', 'unit_price', 'total_price', 'match_count'
    ]
    list_filter = ['quote__status', 'manufacturer', 'is_quote_price']
    search_fields = ['part_number', 'description', 'manufacturer', 'quote__vendor_company']
    readonly_fields = ['created_at', 'updated_at', 'extraction_confidence', 'raw_extracted_data']
    
    inlines = [ProductMatchInline]
    
    fieldsets = (
        ('Quote Information', {
            'fields': ('quote', 'line_number')
        }),
        ('Product Details', {
            'fields': ('part_number', 'description', 'manufacturer', 'vendor_sku')
        }),
        ('Pricing', {
            'fields': ('quantity', 'unit_price', 'total_price', 'is_quote_price', 'price_confidence')
        }),
        ('Extraction Data', {
            'fields': ('extraction_confidence', 'notes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Debug', {
            'fields': ('raw_extracted_data',),
            'classes': ('collapse',)
        })
    )
    
    def description_truncated(self, obj):
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_truncated.short_description = 'Description'
    
    def match_count(self, obj):
        count = obj.matches.count()
        if count > 0:
            url = reverse('admin:quotes_productmatch_changelist') + f'?quote_item__id={obj.id}'
            return format_html('<a href="{}">{} matches</a>', url, count)
        return '0 matches'
    match_count.short_description = 'Matches'

@admin.register(ProductMatch)
class ProductMatchAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'quote_item', 'product', 'confidence', 'is_exact_match',
        'match_method', 'price_difference', 'is_demo_price'
    ]
    list_filter = ['is_exact_match', 'match_method', 'is_demo_price', 'demo_generated_product']
    search_fields = [
        'quote_item__part_number', 'quote_item__description', 
        'product__name', 'product__part_number'
    ]
    readonly_fields = ['created_at', 'updated_at', 'match_details']
    
    fieldsets = (
        ('Match Information', {
            'fields': ('quote_item', 'product', 'suggested_product')
        }),
        ('Match Quality', {
            'fields': ('confidence', 'is_exact_match', 'match_method')
        }),
        ('Pricing Comparison', {
            'fields': ('price_difference', 'price_difference_percentage')
        }),
        ('Demo Mode', {
            'fields': ('is_demo_price', 'demo_generated_product')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Match Details', {
            'fields': ('match_details',),
            'classes': ('collapse',)
        })
    )

@admin.register(VendorPricing)
class VendorPricingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'vendor_company', 'product', 'part_number_used',
        'quoted_price', 'quantity', 'quote_date', 'is_confirmed'
    ]
    list_filter = ['vendor_company', 'is_confirmed', 'quote_date']
    search_fields = [
        'vendor_company', 'vendor_name', 'part_number_used',
        'product__name', 'product__part_number'
    ]
    readonly_fields = ['created_at', 'updated_at', 'source_quote', 'source_quote_item']
    
    fieldsets = (
        ('Vendor Information', {
            'fields': ('vendor_company', 'vendor_name')
        }),
        ('Product & Pricing', {
            'fields': ('product', 'part_number_used', 'quoted_price', 'quantity')
        }),
        ('Quote Information', {
            'fields': ('quote_date', 'source_quote', 'source_quote_item')
        }),
        ('Confirmation', {
            'fields': ('is_confirmed', 'confirmation_date', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

# Add some admin actions
def mark_as_confirmed(modeladmin, request, queryset):
    """Mark vendor pricing as confirmed"""
    from django.utils import timezone
    
    updated = queryset.update(
        is_confirmed=True,
        confirmation_date=timezone.now().date()
    )
    
    modeladmin.message_user(
        request,
        f'{updated} pricing records marked as confirmed.'
    )

mark_as_confirmed.short_description = "Mark selected pricing as confirmed"

def reprocess_quotes(modeladmin, request, queryset):
    """Reprocess selected quotes"""
    from django_q.tasks import async_task
    
    count = 0
    for quote in queryset.filter(status__in=['error', 'completed']):
        async_task(
            'quotes.tasks.match_quote_products',
            quote.id,
            quote.demo_mode_enabled,
            group='quote_reprocessing'
        )
        count += 1
    
    modeladmin.message_user(
        request,
        f'{count} quotes queued for reprocessing.'
    )

reprocess_quotes.short_description = "Reprocess selected quotes"

# Add actions to admin classes
VendorPricingAdmin.actions = [mark_as_confirmed]
QuoteAdmin.actions = [reprocess_quotes]