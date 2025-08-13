from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

# Quote status choices
QUOTE_STATUS_CHOICES = [
    ('uploading', 'Uploading'),
    ('parsing', 'Parsing PDF'),
    ('matching', 'Matching Products'),
    ('completed', 'Completed'),
    ('error', 'Error'),
]

# Product matching method choices
MATCH_METHOD_CHOICES = [
    ('exact_part_number', 'Exact Part Number'),
    ('fuzzy_part_number', 'Fuzzy Part Number Match'),
    ('manufacturer_match', 'Manufacturer + Description'),
    ('description_similarity', 'Description Similarity'),
    ('demo_generated', 'Demo Generated'),
    ('manual', 'Manual Match'),
]

class Quote(models.Model):
    """PDF quote uploaded by user for analysis and product matching"""
    
    # User relationship
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quotes')
    
    # Quote metadata from PDF
    vendor_name = models.CharField(max_length=255, blank=True)
    vendor_company = models.CharField(max_length=255, blank=True)
    quote_number = models.CharField(max_length=100, blank=True)
    quote_date = models.DateField(null=True, blank=True)
    
    # File storage
    pdf_file = models.FileField(upload_to='quotes/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255)
    pdf_content = models.BinaryField(null=True, blank=True, help_text="Raw PDF content for Heroku processing")
    
    # Financial totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tax = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    shipping = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Processing status
    status = models.CharField(max_length=20, choices=QUOTE_STATUS_CHOICES, default='uploading')
    
    # Processing metadata
    openai_task_id = models.CharField(max_length=100, blank=True, help_text="Task ID for OpenAI processing")
    parsing_error = models.TextField(blank=True, help_text="Error message if parsing failed")
    raw_openai_response = models.JSONField(null=True, blank=True, help_text="Raw response from OpenAI for debugging")
    
    # Demo mode flag
    demo_mode_enabled = models.BooleanField(default=False, help_text="Whether demo mode was enabled for this quote")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True, help_text="When processing completed")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['vendor_company']),
        ]
    
    def __str__(self):
        return f"Quote {self.quote_number or self.id} from {self.vendor_company or self.vendor_name or 'Unknown Vendor'}"
    
    @property
    def item_count(self):
        """Return the number of line items in this quote"""
        return self.items.count()
    
    @property
    def matched_item_count(self):
        """Return the number of items that have product matches"""
        return self.items.filter(matches__isnull=False).distinct().count()

class QuoteItem(models.Model):
    """Individual line item from a quote"""
    
    # Quote relationship
    quote = models.ForeignKey(Quote, related_name='items', on_delete=models.CASCADE)
    
    # Line item data from PDF
    line_number = models.IntegerField(null=True, blank=True, help_text="Line number from original quote")
    part_number = models.CharField(max_length=200, db_index=True)
    description = models.TextField()
    manufacturer = models.CharField(max_length=255, blank=True)
    
    # Quantities and pricing
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Additional details
    vendor_sku = models.CharField(max_length=100, blank=True, help_text="Vendor's SKU for this item")
    notes = models.TextField(blank=True, help_text="Additional notes from quote")
    
    # Pricing intelligence flags
    is_quote_price = models.BooleanField(default=True, help_text="Whether this is a quote price vs confirmed price")
    price_confidence = models.FloatField(default=1.0, help_text="Confidence in extracted price (0.0-1.0)")
    
    # Processing metadata
    extraction_confidence = models.FloatField(default=1.0, help_text="Confidence in data extraction (0.0-1.0)")
    raw_extracted_data = models.JSONField(null=True, blank=True, help_text="Raw extracted data for debugging")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['line_number', 'id']
        indexes = [
            models.Index(fields=['quote', 'line_number']),
            models.Index(fields=['part_number']),
            models.Index(fields=['manufacturer', 'part_number']),
        ]
    
    def __str__(self):
        return f"{self.part_number} - {self.description[:50]}..."
    
    @property
    def best_match(self):
        """Return the highest confidence product match"""
        return self.matches.order_by('-confidence').first()
    
    @property
    def has_exact_match(self):
        """Return True if there's an exact product match"""
        return self.matches.filter(is_exact_match=True).exists()

class ProductMatch(models.Model):
    """Represents a match between a quote item and a product in our database"""
    
    # Relationships
    quote_item = models.ForeignKey(QuoteItem, related_name='matches', on_delete=models.CASCADE)
    product = models.ForeignKey('products.Product', null=True, blank=True, on_delete=models.SET_NULL, related_name='quote_matches')
    
    # Match quality metrics
    confidence = models.FloatField(help_text="Match confidence score (0.0-1.0)")
    is_exact_match = models.BooleanField(default=False, help_text="Whether this is considered an exact match")
    match_method = models.CharField(max_length=30, choices=MATCH_METHOD_CHOICES)
    
    # Price comparison
    price_difference = models.DecimalField(max_digits=10, decimal_places=2, help_text="Difference between quote price and our price")
    price_difference_percentage = models.FloatField(help_text="Price difference as percentage")
    
    # Demo mode
    is_demo_price = models.BooleanField(default=False, help_text="Whether this uses demo pricing")
    demo_generated_product = models.BooleanField(default=False, help_text="Whether the product was created for demo")
    
    # Suggested alternatives
    suggested_product = models.ForeignKey(
        'products.Product', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='quote_suggestions',
        help_text="Alternative product suggestion"
    )
    
    # Match details
    match_details = models.JSONField(null=True, blank=True, help_text="Additional matching algorithm details")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-confidence', '-is_exact_match']
        indexes = [
            models.Index(fields=['quote_item', '-confidence']),
            models.Index(fields=['product']),
            models.Index(fields=['is_exact_match']),
            models.Index(fields=['match_method']),
        ]
    
    def __str__(self):
        product_name = self.product.name if self.product else "No Product"
        return f"Match: {self.quote_item.part_number} -> {product_name} ({self.confidence:.2f})"
    
    @property
    def is_better_price(self):
        """Return True if our price is better than the quote price"""
        return self.price_difference < 0

class VendorPricing(models.Model):
    """Store pricing intelligence from quotes for future negotiations"""
    
    # Product and vendor relationships
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='vendor_pricing')
    vendor_company = models.CharField(max_length=255, db_index=True)
    vendor_name = models.CharField(max_length=255, blank=True)
    
    # Pricing data
    quoted_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField()
    quote_date = models.DateField()
    
    # Source information
    source_quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='pricing_records')
    source_quote_item = models.ForeignKey(QuoteItem, on_delete=models.CASCADE, related_name='pricing_records')
    
    # Confirmation status
    is_confirmed = models.BooleanField(default=False, help_text="Whether this pricing has been confirmed")
    confirmation_date = models.DateField(null=True, blank=True)
    
    # Additional context
    part_number_used = models.CharField(max_length=200, help_text="Part number as it appeared in the quote")
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-quote_date', '-created_at']
        indexes = [
            models.Index(fields=['product', 'vendor_company']),
            models.Index(fields=['vendor_company', '-quote_date']),
            models.Index(fields=['part_number_used']),
            models.Index(fields=['quote_date']),
        ]
        unique_together = ['source_quote', 'source_quote_item']  # Prevent duplicate records
    
    def __str__(self):
        return f"{self.vendor_company}: {self.part_number_used} @ ${self.quoted_price}"