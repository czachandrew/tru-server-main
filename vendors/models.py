from django.db import models

# Create your models here.

VENDOR_TYPE_CHOICES = [
    ('supplier', 'Direct Supplier'),
    ('affiliate', 'Affiliate Marketplace'),
    ('distributor', 'Distributor'),
]

class Vendor(models.Model):
    """Sources for product inventory - supports both direct suppliers and affiliate marketplaces"""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, null=True, blank=True, help_text="URL-friendly version of name")
    code = models.CharField(max_length=20, unique=True)  # Internal code
    
    # HYBRID APPROACH: Distinguish between business models
    vendor_type = models.CharField(
        max_length=20,
        choices=VENDOR_TYPE_CHOICES,
        default='supplier',
        help_text="Type of vendor relationship"
    )
    
    # Public info
    website = models.URLField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    
    # Contact info (mainly for direct suppliers)
    contact_name = models.CharField(max_length=100, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    
    # API integration (mainly for direct suppliers)
    api_endpoint = models.URLField(max_length=500, blank=True)
    api_credentials = models.JSONField(blank=True, null=True)  # Encrypted in production
    
    # Business terms (mainly for direct suppliers)
    payment_terms = models.CharField(max_length=100, blank=True)
    shipping_terms = models.TextField(blank=True)
    
    # Affiliate-specific fields
    is_affiliate = models.BooleanField(default=False, help_text="Whether this is an affiliate marketplace")
    affiliate_program = models.CharField(max_length=100, blank=True, help_text="Name of affiliate program")
    default_commission_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Default commission rate for this affiliate vendor"
    )
    
    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['vendor_type']),
            models.Index(fields=['is_affiliate']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        vendor_symbol = "🔗" if self.is_affiliate else "📦"
        return f"{vendor_symbol} {self.name}"
    
    def save(self, *args, **kwargs):
        """Auto-generate slug and sync affiliate flag"""
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        
        # Sync is_affiliate with vendor_type
        self.is_affiliate = (self.vendor_type == 'affiliate')
        
        super().save(*args, **kwargs)