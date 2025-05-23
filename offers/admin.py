from django.contrib import admin
from .models import Offer

@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'product_name', 'vendor_name', 'selling_price', 'get_is_active')
    list_filter = ('vendor', 'is_active')
    search_fields = ('product__name', 'vendor__name', 'vendor_sku')
    raw_id_fields = ('product', 'vendor')
    readonly_fields = ('created_at', 'updated_at', 'availability_updated_at')
    
    def product_name(self, obj):
        return obj.product.name if obj.product else "No Product"
    product_name.short_description = "Product"
    
    def vendor_name(self, obj):
        return obj.vendor.name if obj.vendor else "No Vendor"
    vendor_name.short_description = "Vendor"
    
    def get_is_active(self, obj):
        return obj.is_active
    get_is_active.boolean = True
    get_is_active.short_description = "Active"
    
    fieldsets = (
        (None, {
            'fields': ('product', 'vendor', 'vendor_sku', 'vendor_url')
        }),
        ('Pricing', {
            'fields': ('cost_price', 'selling_price', 'msrp')
        }),
        ('Inventory', {
            'fields': ('stock_quantity', 'is_in_stock')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'availability_updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('product', 'vendor')
