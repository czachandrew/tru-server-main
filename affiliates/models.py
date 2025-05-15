from django.db import models
from products.models import Product

PLATFORM_CHOICES = [
    ('amazon', 'Amazon'),
    ('ebay', 'eBay'),
    ('walmart', 'Walmart'),
    ('other', 'Other')
]

class AffiliateLink(models.Model):
    """Tracking links for affiliate marketing"""
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='affiliate_links')
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES)  # e.g., 'amazon', 'ebay'
    
    # Platform-specific IDs
    platform_id = models.CharField(max_length=100)  # e.g., ASIN for Amazon
    
    # Link details
    original_url = models.TextField()
    affiliate_url = models.TextField()
    
    # Performance tracking
    clicks = models.IntegerField(default=0)
    conversions = models.IntegerField(default=0)
    revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'platform'],
                name='unique_product_platform_link'
            )
        ]
    
    def __str__(self):
        return f"{self.product.name} on {self.platform}"