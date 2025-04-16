# Create your models here.
from django.db import models
from products.models import Product
from vendors.models import Vendor

class Offer(models.Model):
    """A specific product offering from a vendor at a specific price"""
    product = models.ForeignKey(Product, related_name='offers', on_delete=models.CASCADE)
    vendor = models.ForeignKey(Vendor, related_name='offers', on_delete=models.CASCADE)
    
    # Pricing
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)  # Our cost (private)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)  # Our selling price
    msrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Manufacturer's suggested price
    
    # Vendor details
    vendor_sku = models.CharField(max_length=100, blank=True)  # Vendor's own SKU
    vendor_url = models.URLField(max_length=500, blank=True)
    
    # Availability
    stock_quantity = models.IntegerField(default=0)
    is_in_stock = models.BooleanField(default=True)
    availability_updated_at = models.DateTimeField(auto_now=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'vendor'],
                name='unique_product_vendor_offer'
            )
        ]
    
    def __str__(self):
        return f"{self.product.name} - {self.vendor.name} - ${self.selling_price}"