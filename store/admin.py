from django.contrib import admin
from django.utils.html import format_html
from .models import Cart, CartItem


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = [
        'id', 
        'user_display', 
        'session_id_short', 
        'item_count', 
        'total_price_formatted', 
        'created_at', 
        'updated_at'
    ]
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__username', 'user__email', 'session_id']
    readonly_fields = ['created_at', 'updated_at', 'item_count', 'total_price']
    list_per_page = 25
    ordering = ['-updated_at']
    
    fieldsets = (
        ('Cart Information', {
            'fields': ('user', 'session_id')
        }),
        ('Statistics', {
            'fields': ('item_count', 'total_price'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_display(self, obj):
        """Display user information in a friendly format"""
        if obj.user:
            return format_html(
                '<strong>{}</strong><br/><small>{}</small>',
                obj.user.username,
                obj.user.email
            )
        return format_html(
            '<em>Anonymous</em><br/><small>Session: {}</small>',
            obj.session_id[:12] + '...' if len(obj.session_id) > 12 else obj.session_id
        )
    user_display.short_description = 'User'
    user_display.allow_tags = True
    
    def session_id_short(self, obj):
        """Display shortened session ID for anonymous users"""
        if obj.session_id and not obj.user:
            return obj.session_id[:12] + '...' if len(obj.session_id) > 12 else obj.session_id
        return '-'
    session_id_short.short_description = 'Session ID'
    
    def total_price_formatted(self, obj):
        """Display formatted total price"""
        price = obj.total_price
        if price > 0:
            return format_html('<strong>${:.2f}</strong>', price)
        return '$0.00'
    total_price_formatted.short_description = 'Total Price'
    total_price_formatted.allow_tags = True
    
    def get_queryset(self, request):
        """Optimize queryset with prefetch_related"""
        return super().get_queryset(request).select_related('user').prefetch_related('items__offer__product')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'cart_info',
        'product_info',
        'quantity',
        'unit_price_formatted',
        'total_price_formatted',
        'added_at',
        'updated_at'
    ]
    list_filter = ['added_at', 'updated_at', 'offer__offer_type']
    search_fields = [
        'cart__user__username', 
        'cart__user__email',
        'cart__session_id',
        'offer__product__name', 
        'offer__product__part_number'
    ]
    readonly_fields = ['added_at', 'updated_at', 'unit_price', 'total_price']
    list_per_page = 25
    ordering = ['-updated_at']
    
    fieldsets = (
        ('Cart Item Information', {
            'fields': ('cart', 'offer', 'quantity')
        }),
        ('Pricing', {
            'fields': ('unit_price', 'total_price'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('added_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def cart_info(self, obj):
        """Display cart information"""
        if obj.cart.user:
            return format_html(
                'Cart #{}<br/><small>{}</small>',
                obj.cart.id,
                obj.cart.user.username
            )
        return format_html(
            'Cart #{}<br/><small>Anonymous</small>',
            obj.cart.id
        )
    cart_info.short_description = 'Cart'
    cart_info.allow_tags = True
    
    def product_info(self, obj):
        """Display product information"""
        product = obj.offer.product
        return format_html(
            '<strong>{}</strong><br/><small>Part: {}</small>',
            product.name[:40] + '...' if len(product.name) > 40 else product.name,
            product.part_number
        )
    product_info.short_description = 'Product'
    product_info.allow_tags = True
    
    def unit_price_formatted(self, obj):
        """Display formatted unit price"""
        return f'${obj.unit_price:.2f}'
    unit_price_formatted.short_description = 'Unit Price'
    
    def total_price_formatted(self, obj):
        """Display formatted total price"""
        return format_html('<strong>${:.2f}</strong>', obj.total_price)
    total_price_formatted.short_description = 'Total Price'
    total_price_formatted.allow_tags = True
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'cart__user', 
            'offer__product', 
            'offer__vendor'
        )

