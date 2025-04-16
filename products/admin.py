from django.contrib import admin
from .models import Product, Category, Manufacturer, ProductCategory

class ProductCategoryInline(admin.TabularInline):
    model = ProductCategory
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'part_number', 'manufacturer', 'status')
    list_filter = ('status', 'manufacturer', 'categories')
    search_fields = ('name', 'part_number', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductCategoryInline]

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'is_visible')
    list_filter = ('is_visible', 'parent')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ('name', 'website')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}