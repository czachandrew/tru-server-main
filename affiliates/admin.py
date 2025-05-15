from django.contrib import admin
from .models import AffiliateLink
from .tasks import generate_amazon_affiliate_url
from django.utils import timezone

def requeue_selected_links(modeladmin, request, queryset):
    success = 0
    for link in queryset:
        if link.platform == 'amazon':
            # Use our webhook-based generation function
            result = generate_amazon_affiliate_url(link.id, link.platform_id)
            if result:
                success += 1
                # Instead of using notes field, we could use the affiliate_url field to indicate requeued status
                # or just skip this part entirely since we don't have a notes field
    
    modeladmin.message_user(request, f"Requeued {success} affiliate links for processing")

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
