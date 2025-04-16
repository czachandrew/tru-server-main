from django.db import models

# Create your models here.


class Vendor(models.Model):
    """Sources for product inventory"""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)  # Internal code
    
    # Contact info
    contact_name = models.CharField(max_length=100, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    
    # API integration
    api_endpoint = models.URLField(max_length=500, blank=True)
    api_credentials = models.JSONField(blank=True, null=True)  # Encrypted in production
    
    # Terms
    payment_terms = models.CharField(max_length=100, blank=True)
    shipping_terms = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name