from django.db import models
from products.models import Product
from django.utils import timezone
from decimal import Decimal
import logging
logger = logging.getLogger('affiliate_tasks')

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

class AffiliateClickEvent(models.Model):
    """Track affiliate link clicks detected by the browser extension"""
    
    CLICK_SOURCES = [
        ('extension', 'Browser Extension'),
        ('website', 'Website Direct'),
        ('email', 'Email Campaign'),
        ('social', 'Social Media'),
        ('other', 'Other'),
    ]
    
    # User and affiliate link reference
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='affiliate_clicks',
        help_text="User who clicked the affiliate link"
    )
    
    affiliate_link = models.ForeignKey(
        'AffiliateLink',
        on_delete=models.CASCADE,
        related_name='click_events',
        help_text="Affiliate link that was clicked"
    )
    
    # Click details
    source = models.CharField(
        max_length=20,
        choices=CLICK_SOURCES,
        default='extension',
        help_text="Source of the click (extension, website, etc.)"
    )
    
    # Extension-provided data
    session_id = models.CharField(
        max_length=100,
        help_text="Extension-generated session ID for tracking"
    )
    
    referrer_url = models.TextField(
        blank=True,
        help_text="URL where the user was when they clicked"
    )
    
    target_domain = models.CharField(
        max_length=100,
        help_text="Domain user was redirected to (amazon.com, ebay.com, etc.)"
    )
    
    # Product context
    product_data = models.JSONField(
        default=dict,
        help_text="Product details as detected by extension"
    )
    
    # Browser/device context
    user_agent = models.TextField(blank=True)
    browser_fingerprint = models.CharField(max_length=100, blank=True)
    
    # Tracking metadata
    clicked_at = models.DateTimeField(auto_now_add=True)
    
    # Session tracking
    session_duration = models.IntegerField(
        null=True,
        blank=True,
        help_text="Time spent on target site in seconds"
    )
    
    session_ended_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this click is still being tracked"
    )
    
    class Meta:
        ordering = ['-clicked_at']
        indexes = [
            models.Index(fields=['user', 'clicked_at']),
            models.Index(fields=['affiliate_link', 'clicked_at']),
            models.Index(fields=['session_id']),
            models.Index(fields=['target_domain']),
        ]
    
    def __str__(self):
        return f"{self.user.email} clicked {self.affiliate_link} at {self.clicked_at}"
    
    def update_session_duration(self, duration_seconds):
        """Update session duration when extension reports it"""
        self.session_duration = duration_seconds
        self.session_ended_at = self.clicked_at + timezone.timedelta(seconds=duration_seconds)
        self.save(update_fields=['session_duration', 'session_ended_at'])


class PurchaseIntentEvent(models.Model):
    """Track purchase intent detected by the browser extension"""
    
    INTENT_STAGES = [
        ('cart_add', 'Added to Cart'),
        ('cart_view', 'Viewing Cart'),
        ('shipping_info', 'Entered Shipping Info'),
        ('payment_page', 'Reached Payment Page'),
        ('payment_info', 'Entered Payment Info'),
        ('order_review', 'Order Review'),
        ('order_submit', 'Order Submitted'),
        ('order_confirmed', 'Order Confirmed'),
    ]
    
    CONFIDENCE_LEVELS = [
        ('LOW', 'Low (30-50%)'),
        ('MEDIUM', 'Medium (50-70%)'),
        ('HIGH', 'High (70-90%)'),
        ('VERY_HIGH', 'Very High (90%+)'),
    ]
    
    # Related click event
    click_event = models.ForeignKey(
        'AffiliateClickEvent',
        on_delete=models.CASCADE,
        related_name='purchase_intents',
        help_text="Original click event that led to this purchase intent"
    )
    
    # Purchase details
    intent_stage = models.CharField(
        max_length=20,
        choices=INTENT_STAGES,
        help_text="Stage of purchase process detected"
    )
    
    confidence_level = models.CharField(
        max_length=10,
        choices=CONFIDENCE_LEVELS,
        help_text="Confidence level of purchase intent"
    )
    
    confidence_score = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text="Numerical confidence score (0.00-1.00)"
    )
    
    # Cart/order details
    cart_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total cart value if detected"
    )
    
    cart_items = models.JSONField(
        default=list,
        help_text="List of items in cart as detected by extension"
    )
    
    # Product matching
    matched_products = models.JSONField(
        default=list,
        help_text="Products that match original affiliate link"
    )
    
    # Page context
    page_url = models.TextField(help_text="URL where intent was detected")
    page_title = models.CharField(max_length=255, blank=True)
    
    # Timestamps
    detected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Processing status
    has_created_projection = models.BooleanField(
        default=False,
        help_text="Whether a projected earning was created for this intent"
    )
    
    projected_transaction = models.OneToOneField(
        'users.WalletTransaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_intent',
        help_text="Projected wallet transaction created from this intent"
    )
    
    class Meta:
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['click_event', 'detected_at']),
            models.Index(fields=['intent_stage', 'confidence_level']),
            models.Index(fields=['has_created_projection']),
            models.Index(fields=['detected_at']),
        ]
    
    def __str__(self):
        return f"{self.click_event.user.email} - {self.intent_stage} ({self.confidence_level})"
    
    @property
    def user(self):
        """Get user from related click event"""
        return self.click_event.user
    
    @property
    def affiliate_link(self):
        """Get affiliate link from related click event"""
        return self.click_event.affiliate_link
    
    def should_create_projection(self):
        """Determine if this intent should create a projected earning"""
        # Only create projections for medium confidence or higher
        if self.confidence_level in ['MEDIUM', 'HIGH', 'VERY_HIGH']:
            return True
        
        # Or if user has high historical conversion rate
        user_conversion_rate = self.calculate_user_conversion_rate()
        if user_conversion_rate > 0.3:  # 30% historical conversion rate
            return True
        
        return False
    
    def calculate_user_conversion_rate(self):
        """Calculate user's historical conversion rate"""
        # This would be implemented based on historical data
        # For now, return a default value
        return 0.2  # 20% default conversion rate
    
    def calculate_projected_commission(self):
        """Calculate projected commission amount for affiliate links"""
        from decimal import Decimal
        import json
        affiliate_link = self.affiliate_link

        # 1. Try to get price from product_data (extension)
        price = None
        pd = getattr(self, 'product_data', None)
        logger.info(f"[CommissionCalc] Raw product_data: {pd}")
        if pd:
            if isinstance(pd, str):
                try:
                    pd = json.loads(pd)
                except Exception:
                    pd = {}
            price = pd.get('price')
            if price:
                try:
                    price = Decimal(str(price))
                except Exception:
                    logger.warning(f"[CommissionCalc] Could not convert price '{price}' to Decimal.")
                    price = None
        
        # 2. Fallback to offer's selling_price
        offer = affiliate_link.product.offers.filter(is_active=True).order_by('-selling_price').first()
        if not price and offer and hasattr(offer, 'selling_price') and offer.selling_price:
            price = Decimal(str(offer.selling_price))
            logger.info(f"[CommissionCalc] Using offer selling_price: {price}")
        if not price:
            logger.error(f"[CommissionCalc] No price found for PurchaseIntentEvent {self.id}. Cannot calculate commission.")
            raise ValueError(f"No price found for PurchaseIntentEvent {self.id} (product: {affiliate_link.product.id})")

        # 3. Use commission rate: affiliate link > offer > default 2%
        commission_rate = affiliate_link.commission_rate
        if commission_rate is None and offer and getattr(offer, 'commission_rate', None):
            commission_rate = Decimal(str(offer.commission_rate))
            logger.info(f"[CommissionCalc] Using offer commission_rate: {commission_rate}")
        elif commission_rate is None:
            commission_rate = Decimal('0.02')  # 2% default
            logger.warning(f"[CommissionCalc] No commission_rate found, defaulting to 2% for PurchaseIntentEvent {self.id}")
        else:
            commission_rate = Decimal(str(commission_rate))

        commission_amount = price * (commission_rate / Decimal('100'))

        # 4. Apply user's revenue share rate
        user_share_rate = self.user.profile.revenue_share_rate
        logger.info(f"[CommissionCalc] User share rate: {user_share_rate}")
        commission_amount = commission_amount * user_share_rate

        logger.info(
            f"[CommissionCalc] Commission calculation for PurchaseIntentEvent {self.id}: "
            f"price={price}, commission_rate={commission_rate}, "
            f"user_share_rate={user_share_rate}, commission_amount={commission_amount}"
        )

        # 5. Round to 2 decimal places
        return commission_amount.quantize(Decimal('0.01'))
    
    def create_projected_earning(self):
        print(f"[DEBUG] create_projected_earning called for PurchaseIntentEvent {self.id} (intent_stage={self.intent_stage})")
        from users.models import WalletTransaction

        if self.intent_stage != 'cart_view':
            print(f"[DEBUG] Skipping: intent_stage is {self.intent_stage}, not 'cart_view'.")
            return None

        if self.has_created_projection or WalletTransaction.objects.filter(
            user=self.user,
            affiliate_link=self.affiliate_link,
            transaction_type='EARNING_PROJECTED',
            metadata__purchase_intent_id=self.id
        ).exists():
            print(f"[DEBUG] Skipping: already has created projection for PurchaseIntentEvent {self.id}.")
            return self.projected_transaction

        if not self.should_create_projection():
            print(f"[DEBUG] Skipping: should_create_projection() returned False for {self.id}.")
            return None

        try:
            projected_amount = self.calculate_projected_commission()
        except Exception as e:
            print(f"[DEBUG] Failed to calculate commission: {e}")
            raise

        print(f"[DEBUG] Creating WalletTransaction for user {self.user.id} with amount {projected_amount}")

        transaction = WalletTransaction.objects.create(
            user=self.user,
            transaction_type='EARNING_PROJECTED',
            amount=projected_amount,
            balance_before=self.user.profile.pending_balance,
            balance_after=self.user.profile.pending_balance + projected_amount,
            affiliate_link=self.affiliate_link,
            description=f"Projected earning from {self.intent_stage} on {self.affiliate_link.platform}",
            metadata={
                'purchase_intent_id': self.id,
                'confidence_level': self.confidence_level,
                'confidence_score': float(self.confidence_score),
                'intent_stage': self.intent_stage,
                'cart_total': float(self.cart_total) if self.cart_total else None,
                'detection_method': 'extension_checkout_detection',
            }
        )

        self.user.profile.pending_balance += projected_amount
        self.user.profile.save(update_fields=['pending_balance'])

        self.projected_transaction = transaction
        self.has_created_projection = True
        self.save(update_fields=['projected_transaction', 'has_created_projection'])

        # Create referral disbursements if user has active codes
        self.create_referral_disbursements(transaction, projected_amount)

        print(f"[DEBUG] WalletTransaction {transaction.id} created for user {self.user.id} (amount={projected_amount})")

        return transaction
    
    def create_referral_disbursements(self, wallet_transaction, commission_amount):
        """Create referral disbursements for user's active codes (locked at purchase time)"""
        from users.models import UserReferralCode, ReferralDisbursement
        from users.services import ReferralCodeService
        
        # Get user's active codes at purchase time
        active_codes = UserReferralCode.objects.filter(
            user=self.user,
            is_active=True
        ).select_related('referral_code', 'referral_code__promotion')
        
        # Filter codes that are within valid promotion timeline
        valid_codes = []
        for user_code in active_codes:
            promotion = user_code.referral_code.promotion
            if (promotion and promotion.is_active and 
                promotion.is_purchase_period_open()):
                valid_codes.append(user_code)
        
        if not valid_codes:
            print(f"[DEBUG] No valid referral codes for user {self.user.id}")
            return
        
        # Calculate allocations for valid codes only (locked at purchase time)
        allocations = ReferralCodeService.calculate_user_allocations(self.user)
        
        print(f"[DEBUG] Creating disbursements for {len(valid_codes)} valid codes")
        
        # Create disbursement records (immutable)
        for user_code in valid_codes:
            code_id = user_code.referral_code.id
            if code_id in allocations.get('codes', {}):
                disbursement_amount = commission_amount * (Decimal(str(allocations['codes'][code_id])) / Decimal('100'))
                
                disbursement = ReferralDisbursement.objects.create(
                    wallet_transaction=wallet_transaction,
                    referral_code=user_code.referral_code,
                    recipient_user=user_code.referral_code.owner,
                    amount=disbursement_amount,
                    allocation_percentage=allocations['codes'][code_id],
                    status='pending'
                )
                
                print(f"[DEBUG] Created disbursement {disbursement.id}: ${disbursement_amount} to {user_code.referral_code.owner.email}")
        
        print(f"[DEBUG] Created {len(valid_codes)} referral disbursements for user {self.user.id}")