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
    list_display = ('name', 'part_number', 'manufacturer_name')
    list_filter = ('manufacturer',)
    search_fields = ('name', 'part_number', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductCategoryInline, AffiliateInline]
    readonly_fields = ('created_at', 'updated_at')
    
    def manufacturer_name(self, obj):
        return obj.manufacturer.name if obj.manufacturer else "No Manufacturer"
    manufacturer_name.short_description = "Manufacturer"

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