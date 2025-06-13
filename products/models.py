from django.db import models
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
# Create your models here.
PRODUCT_STATUS_CHOICES = [
    ('active', 'Active'),
    ('inactive', 'Inactive'),
    ('discontinued', 'Discontinued'),
    ('pending', 'Pending'),
    ('future_opportunity', 'Future Opportunity')
]

PRODUCT_SOURCE_CHOICES = [
    ('amazon', 'Amazon'),
    ('web_scrape', 'Web Scrape'),
    ('partner_import', 'Partner Import'),
    ('manual', 'Manual Entry'),
    ('user_contributed', 'User Contributed'),
    ('future_demand', 'Future Demand Tracking')
]

class Manufacturer(models.Model):
    """Brand or manufacturer information"""
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    logo = models.URLField(max_length=500, blank=True)
    website = models.URLField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    


class Category(models.Model):
    """Product Categorization Heirarchy"""
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    image = models.URLField(max_length=500, blank=True)

    display_order = models.IntegerField(default=0)
    is_visible = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name
    
class Product(models.Model):
    """ Universla product information seperate from vendor"""
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    specifications = models.JSONField(blank=True, null=True)

    #Identifiers 
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.CASCADE, related_name='products')
    part_number = models.CharField(max_length=100, db_index=True)

    #Categorization
    categories = models.ManyToManyField(Category, through='ProductCategory')

    #Physical Attributes 
    weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    dimensions = models.JSONField(null=True, blank=True)  # {length, width, height}
    
    # Media
    main_image = models.URLField(max_length=500, blank=True)
    additional_images = models.JSONField(blank=True, null=True)  # Array of image URLs
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=PRODUCT_STATUS_CHOICES, default='active')
    source = models.CharField(max_length=20, choices=PRODUCT_SOURCE_CHOICES, default='manual')

    # Add this new field
    is_featured = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False, help_text="Mark this product as demo data for testing/presentations")
    
    # NEW: Future demand tracking for universal search
    future_demand_count = models.IntegerField(default=0, help_text="Number of times this product was searched for")
    last_demand_date = models.DateTimeField(null=True, blank=True, help_text="Last time someone searched for this product")

    # Indicates a minimal placeholder created before full product data is scraped
    is_placeholder = models.BooleanField(default=False, db_index=True)

    class Meta:
        # Comment out the indexes temporarily
        # indexes = [
        #     GinIndex(fields=['search_vector'], name='product_search_index')
        # ]
        constraints = [
            models.UniqueConstraint(
                fields=['manufacturer', 'part_number'],
                name='unique_manufacturer_part'
            )
        ]
        
    def __str__(self):
        return self.name

class ProductCategory(models.Model):
    """Association between Products and Categories with position info"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False)  # Is this the main category?
    position = models.IntegerField(default=0)  # Position within category
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'category'],
                name='unique_product_category'
            )
        ]