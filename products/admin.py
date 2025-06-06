from django.contrib import admin
from .models import Product, Category, Manufacturer, ProductCategory
from django.urls import reverse
from django.utils.html import format_html
from affiliates.models import AffiliateLink

class ProductCategoryInline(admin.TabularInline):
    model = ProductCategory
    extra = 1

class AffiliateInline(admin.TabularInline):
    model = AffiliateLink
    extra = 0
    fields = ('platform', 'platform_id', 'original_url')
    readonly_fields = ('platform', 'platform_id', 'original_url')
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'part_number', 'manufacturer_name', 'is_demo', 'status')
    list_filter = ('manufacturer', 'is_demo', 'status', 'source')
    search_fields = ('name', 'part_number', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductCategoryInline, AffiliateInline]
    readonly_fields = ('created_at', 'updated_at')
    actions = ['mark_as_demo', 'mark_as_production', 'delete_demo_products']
    
    def manufacturer_name(self, obj):
        return obj.manufacturer.name if obj.manufacturer else "No Manufacturer"
    manufacturer_name.short_description = "Manufacturer"
    
    def mark_as_demo(self, request, queryset):
        count = queryset.update(is_demo=True)
        self.message_user(request, f"{count} products marked as demo.")
    mark_as_demo.short_description = "Mark selected products as demo"
    
    def mark_as_production(self, request, queryset):
        count = queryset.update(is_demo=False)
        self.message_user(request, f"{count} products marked as production.")
    mark_as_production.short_description = "Mark selected products as production"
    
    def delete_demo_products(self, request, queryset):
        demo_count = queryset.filter(is_demo=True).count()
        queryset.filter(is_demo=True).delete()
        self.message_user(request, f"{demo_count} demo products deleted.")
    delete_demo_products.short_description = "Delete demo products only"

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_visible')
    list_filter = ('is_visible',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}