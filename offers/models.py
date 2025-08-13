# Create your models here.
from django.db import models
from products.models import Product
from vendors.models import Vendor

OFFER_TYPE_CHOICES = [
    ('supplier', 'Direct Supplier'),
    ('affiliate', 'Affiliate Referral'),
    ('quote', 'Quote-Based Pricing'),
]

class Offer(models.Model):
    """A specific product offering from a vendor at a specific price - supports both supplier and affiliate offers"""
    product = models.ForeignKey(Product, related_name='offers', on_delete=models.CASCADE)
    vendor = models.ForeignKey(Vendor, related_name='offers', on_delete=models.CASCADE)
    
    # HYBRID APPROACH: Offer type distinguishes between business models
    offer_type = models.CharField(
        max_length=20, 
        choices=OFFER_TYPE_CHOICES, 
        default='supplier',
        help_text="Whether this is a direct supplier offer or affiliate referral"
    )
    
    # Pricing (unified for both supplier and affiliate)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Our cost (private, mainly for supplier)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)  # Selling price (from supplier) or current price (from affiliate)
    msrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Manufacturer's suggested price
    
    # Vendor details
    vendor_sku = models.CharField(max_length=100, blank=True)  # Vendor's own SKU or platform ID (ASIN, etc.)
    vendor_url = models.URLField(max_length=500, blank=True)  # Original product URL
    
    # Availability
    stock_quantity = models.IntegerField(default=0)
    is_in_stock = models.BooleanField(default=True)
    availability_updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    # Quote-specific fields (only used when offer_type='quote')
    is_confirmed = models.BooleanField(
        default=True,
        help_text="Whether this price is confirmed/guaranteed (False for quote-based estimates)"
    )
    source_quote = models.ForeignKey(
        'quotes.Quote',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='generated_offers',
        help_text="Source quote if this offer was generated from quote analysis"
    )
    
    # Affiliate-specific fields (only used when offer_type='affiliate')
    commission_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Commission percentage for affiliate offers (e.g., 5.00 for 5%)"
    )
    
    expected_commission = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Calculated expected commission amount"
    )
    
    # Price tracking for affiliate offers
    price_last_updated = models.DateTimeField(null=True, blank=True, help_text="When price was last fetched from affiliate platform")
    price_history = models.JSONField(
        default=list,
        blank=True,
        help_text="Historical price data for tracking price changes"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'vendor', 'offer_type', 'source_quote'],
                name='unique_product_vendor_offer_quote'
            )
        ]
        indexes = [
            models.Index(fields=['offer_type']),
            models.Index(fields=['selling_price']),
            models.Index(fields=['is_active', 'is_in_stock']),
        ]
    
    def __str__(self):
        offer_symbol = "🔗" if self.offer_type == 'affiliate' else "📦"
        return f"{offer_symbol} {self.product.name} - {self.vendor.name} - ${self.selling_price}"
    
    def update_price_history(self, new_price):
        """Add new price to history and update current price"""
        from django.utils import timezone
        
        if not self.price_history:
            self.price_history = []
        
        # Add current price to history before updating
        if self.selling_price and self.selling_price != new_price:
            self.price_history.append({
                'price': float(self.selling_price),
                'timestamp': timezone.now().isoformat(),
            })
        
        # Update current price
        self.selling_price = new_price
        self.price_last_updated = timezone.now()
        
        # Keep only last 100 price points to avoid infinite growth
        if len(self.price_history) > 100:
            self.price_history = self.price_history[-100:]
        
        self.save()
    
    def calculate_expected_commission(self):
        """Calculate expected commission for affiliate offers"""
        if self.offer_type == 'affiliate' and self.commission_rate and self.selling_price:
            commission = (self.selling_price * self.commission_rate) / 100
            self.expected_commission = commission
            return commission
        return None
    
    @property
    def is_affiliate(self):
        """Quick check if this is an affiliate offer"""
        return self.offer_type == 'affiliate'
    
    @property
    def is_supplier(self):
        """Quick check if this is a supplier offer"""
        return self.offer_type == 'supplier'
    
    def save(self, *args, **kwargs):
        """Override save to auto-calculate commission"""
        if self.offer_type == 'affiliate':
            self.calculate_expected_commission()
        super().save(*args, **kwargs)