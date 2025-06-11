from django.db import models
from products.models import Product

PLATFORM_CHOICES = [
    ('amazon', 'Amazon'),
    ('ebay', 'eBay'),
    ('walmart', 'Walmart'),
    ('other', 'Other')
]

ASSOCIATION_TYPE_CHOICES = [
    ('search_alternative', 'Search Alternative'),  # Found when searching for original
    ('same_brand_alternative', 'Same Brand Alternative'),  # Same manufacturer
    ('cross_brand_alternative', 'Cross Brand Alternative'),  # Different manufacturer
    ('upgrade_option', 'Upgrade Option'),  # Better/newer version
    ('budget_option', 'Budget Option'),  # Cheaper alternative
    ('compatible_accessory', 'Compatible Accessory'),  # Works with original
    ('bundle_item', 'Bundle Item'),  # Often bought together
]

class AffiliateLink(models.Model):
    """Tracking links for affiliate marketing - now connected to unified Offer system"""
    
    # HYBRID APPROACH: Link to unified offer system
    offer = models.OneToOneField(
        'offers.Offer', 
        on_delete=models.CASCADE,
        null=True, 
        blank=True,
        related_name='affiliate_link',
        help_text="Connected offer in unified pricing system (for hybrid approach)"
    )
    
    # BACKWARD COMPATIBILITY: Keep direct product relationship
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='affiliate_links')
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES)  # e.g., 'amazon', 'ebay'
    
    # Platform-specific IDs
    platform_id = models.CharField(max_length=100)  # e.g., ASIN for Amazon
    
    # Link details
    original_url = models.TextField()
    affiliate_url = models.TextField()
    
    # Affiliate-specific technical data (preserved from original)
    commission_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Commission percentage (duplicated to Offer for convenience)"
    )
    
    # Performance tracking (enhanced)
    clicks = models.IntegerField(default=0)
    conversions = models.IntegerField(default=0)
    revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Technical metadata
    last_checked = models.DateTimeField(null=True, blank=True, help_text="When affiliate URL was last validated")
    is_url_valid = models.BooleanField(default=True, help_text="Whether the affiliate URL is currently working")
    error_count = models.IntegerField(default=0, help_text="Number of consecutive errors when checking URL")
    
    # Processing state tracking (prevents duplicate task creation)
    is_processing = models.BooleanField(default=False, help_text="Whether affiliate URL generation is currently in progress")
    processing_started_at = models.DateTimeField(null=True, blank=True, help_text="When affiliate URL generation started")
    
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
        indexes = [
            models.Index(fields=['platform']),
            models.Index(fields=['is_active', 'is_url_valid']),
            models.Index(fields=['last_checked']),
        ]
    
    def __str__(self):
        return f"{self.product.name} on {self.platform}"
    
    def sync_with_offer(self):
        """Sync affiliate link data with connected offer"""
        if not self.offer:
            return False
            
        # Update offer with affiliate-specific data
        self.offer.commission_rate = self.commission_rate
        self.offer.vendor_sku = self.platform_id  # ASIN, eBay item ID, etc.
        self.offer.vendor_url = self.original_url
        self.offer.save()
        
        return True
    
    def create_or_update_offer(self, current_price, vendor=None):
        """Create or update the connected offer with current pricing data"""
        from offers.models import Offer
        from vendors.models import Vendor
        
        # Get or create vendor for this platform
        if not vendor:
            vendor, _ = Vendor.objects.get_or_create(
                name=f"{self.platform.title()} Marketplace",
                defaults={
                    'slug': f"{self.platform}-marketplace",
                    'website': f"https://{self.platform}.com",
                    'is_affiliate': True
                }
            )
        
        # Create or update the offer
        offer, created = Offer.objects.update_or_create(
            product=self.product,
            vendor=vendor,
            offer_type='affiliate',
            defaults={
                'selling_price': current_price,
                'vendor_sku': self.platform_id,
                'vendor_url': self.original_url,
                'commission_rate': self.commission_rate,
                'is_in_stock': True,  # Assume in stock unless told otherwise
                'stock_quantity': 999,  # Placeholder for affiliate offers
            }
        )
        
        # Connect the offer to this affiliate link
        self.offer = offer
        self.save(update_fields=['offer'])
        
        return offer, created
    
    def record_click(self):
        """Record a click and update connected offer metrics"""
        self.clicks += 1
        self.save(update_fields=['clicks'])
        
        # TODO: Could also update offer-level metrics if needed
    
    def record_conversion(self, revenue_amount=None):
        """Record a conversion and update revenue"""
        self.conversions += 1
        if revenue_amount:
            self.revenue += revenue_amount
        self.save(update_fields=['conversions', 'revenue'])
    
    @property
    def click_through_rate(self):
        """Calculate CTR if we have impression data"""
        # This would require impression tracking to be meaningful
        return 0.0
    
    @property
    def conversion_rate(self):
        """Calculate conversion rate from clicks"""
        if self.clicks == 0:
            return 0.0
        return (self.conversions / self.clicks) * 100

class ProductAssociation(models.Model):
    """Track relationships between products for intelligent search optimization"""
    
    # The original product that was searched for
    source_product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='associations_as_source',
        null=True,
        blank=True,
        help_text="Original product that was searched for (can be null for search terms)"
    )
    
    # Alternative/related product that was found/offered
    target_product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='associations_as_target',
        help_text="Product that was found as an alternative"
    )
    
    # Search context
    original_search_term = models.CharField(
        max_length=255,
        help_text="Original search term used (e.g., 'Dell XPS keyboard')"
    )
    
    search_context = models.JSONField(
        blank=True,
        null=True,
        help_text="Additional context like browser, product page URL, etc."
    )
    
    # Relationship details
    association_type = models.CharField(
        max_length=30,
        choices=ASSOCIATION_TYPE_CHOICES,
        default='search_alternative'
    )
    
    confidence_score = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=1.00,
        help_text="Confidence score 0.00-1.00 for this association"
    )
    
    # Performance tracking
    search_count = models.IntegerField(
        default=1,
        help_text="Number of times this association was created/reinforced"
    )
    
    click_count = models.IntegerField(
        default=0,
        help_text="Number of times users clicked on this alternative"
    )
    
    conversion_count = models.IntegerField(
        default=0,
        help_text="Number of times this alternative led to purchases"
    )
    
    # Metadata
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    # Source tracking
    created_via_platform = models.CharField(
        max_length=50,
        choices=PLATFORM_CHOICES,
        default='amazon',
        help_text="Platform where this association was discovered"
    )
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['source_product', 'target_product', 'association_type'],
                name='unique_product_association'
            )
        ]
        indexes = [
            models.Index(fields=['original_search_term']),
            models.Index(fields=['association_type']),
            models.Index(fields=['confidence_score']),
            models.Index(fields=['search_count']),
        ]
    
    def __str__(self):
        source_name = self.source_product.name if self.source_product else "Direct Search"
        return f"{source_name} → {self.target_product.name} ({self.association_type})"
    
    def increment_search_count(self):
        """Increment search count and update last_seen"""
        self.search_count += 1
        self.save(update_fields=['search_count', 'last_seen'])
    
    def record_click(self):
        """Record a user click on this alternative"""
        self.click_count += 1
        self.save(update_fields=['click_count'])
    
    def record_conversion(self):
        """Record a purchase/conversion from this alternative"""
        self.conversion_count += 1
        self.save(update_fields=['conversion_count'])
    
    @property
    def click_through_rate(self):
        """Calculate click-through rate"""
        if self.search_count == 0:
            return 0.0
        return (self.click_count / self.search_count) * 100
    
    @property
    def conversion_rate(self):
        """Calculate conversion rate"""
        if self.click_count == 0:
            return 0.0
        return (self.conversion_count / self.click_count) * 100