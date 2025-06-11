from django.contrib import admin
from .models import AffiliateLink, ProductAssociation
from django_q.tasks import async_task

def requeue_selected_links(modeladmin, request, queryset):
    """Admin action to requeue affiliate links for processing"""
    for affiliate_link in queryset:
        if affiliate_link.platform == 'amazon' and affiliate_link.platform_id:
            # Queue the affiliate link generation task
            task_id = async_task(
                'affiliates.tasks.generate_amazon_affiliate_url',
                affiliate_link.id,
                affiliate_link.platform_id
            )
            affiliate_link.affiliate_url = f"QUEUED: {task_id}"
            affiliate_link.save()

requeue_selected_links.short_description = "Requeue selected links for processing"

@admin.register(AffiliateLink)
class AffiliateLinkAdmin(admin.ModelAdmin):
    list_display = ('id', 'product_name', 'platform', 'platform_id', 'is_active', 'has_affiliate_url')
    list_filter = ('platform', 'is_active')
    search_fields = ('product__name', 'platform_id', 'original_url', 'affiliate_url')
    raw_id_fields = ('product',)
    readonly_fields = ('created_at', 'updated_at')
    actions = [requeue_selected_links]
    
    def product_name(self, obj):
        return obj.product.name if obj.product else "No Product"
    product_name.short_description = "Product"
    
    def has_affiliate_url(self, obj):
        return bool(obj.affiliate_url)
    has_affiliate_url.boolean = True
    has_affiliate_url.short_description = "Has Affiliate URL"

    fieldsets = (
        (None, {
            'fields': ('product', 'platform', 'platform_id')
        }),
        ('URLs', {
            'fields': ('original_url', 'affiliate_url')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(ProductAssociation)
class ProductAssociationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'source_product_name', 
        'target_product_name', 
        'association_type', 
        'search_count', 
        'click_count',
        'conversion_count',
        'confidence_score',
        'click_through_rate_percent',
        'conversion_rate_percent',
        'is_active'
    )
    
    list_filter = (
        'association_type', 
        'created_via_platform', 
        'is_active',
        'first_seen'
    )
    
    search_fields = (
        'original_search_term',
        'source_product__name',
        'target_product__name',
        'source_product__part_number',
        'target_product__part_number'
    )
    
    raw_id_fields = ('source_product', 'target_product')
    readonly_fields = ('first_seen', 'last_seen', 'click_through_rate_percent', 'conversion_rate_percent')
    
    ordering = ('-search_count', '-last_seen')
    
    def source_product_name(self, obj):
        return obj.source_product.name if obj.source_product else "Direct Search"
    source_product_name.short_description = "Source Product"
    
    def target_product_name(self, obj):
        return obj.target_product.name
    target_product_name.short_description = "Target Product"
    
    def click_through_rate_percent(self, obj):
        return f"{obj.click_through_rate:.1f}%"
    click_through_rate_percent.short_description = "CTR"
    
    def conversion_rate_percent(self, obj):
        return f"{obj.conversion_rate:.1f}%"
    conversion_rate_percent.short_description = "Conv Rate"

    fieldsets = (
        ('Association Details', {
            'fields': (
                'source_product', 
                'target_product', 
                'association_type',
                'confidence_score'
            )
        }),
        ('Search Context', {
            'fields': (
                'original_search_term',
                'search_context',
                'created_via_platform'
            )
        }),
        ('Performance Metrics', {
            'fields': (
                'search_count',
                'click_count', 
                'conversion_count',
                'click_through_rate_percent',
                'conversion_rate_percent'
            ),
            'classes': ('collapse',)
        }),
        ('Status & Timing', {
            'fields': (
                'is_active',
                'first_seen',
                'last_seen'
            ),
            'classes': ('collapse',)
        }),
    )
