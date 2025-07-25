from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            # For OAuth users, we don't set a password
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    
    # Google OAuth fields
    google_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    avatar = models.URLField(blank=True, null=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    objects = CustomUserManager()
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def __str__(self):
        return self.email


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Original fields
    phone = models.CharField(max_length=20, blank=True)
    company = models.CharField(max_length=100, blank=True)
    
    # Fields from store.UserProfile
    preferred_categories = models.ManyToManyField('products.Category', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stripe_connect_account_id = models.CharField(max_length=128, blank=True, null=True, help_text="Stripe Connect account for payouts")
    preferred_payout_method = models.CharField(
        max_length=20,
        choices=[('stripe_bank', 'Stripe Bank Transfer'), ('paypal', 'PayPal')],
        default='stripe_bank',
        help_text="Preferred payout method"
    )
    paypal_email = models.EmailField(blank=True, null=True, help_text="PayPal email for payouts (if selected)")
    payout_status = models.CharField(
        max_length=20,
        choices=[('eligible', 'Eligible'), ('pending_verification', 'Pending Verification'), ('suspended', 'Suspended')],
        default='pending_verification',
        help_text="Payout eligibility status"
    )
    last_payout_at = models.DateTimeField(blank=True, null=True, help_text="Last payout date")
    
    # Enhanced wallet fields
    available_balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Confirmed balance available for spending/withdrawal"
    )
    pending_balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Projected earnings awaiting confirmation"
    )
    lifetime_earnings = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Total confirmed earnings ever received"
    )
    total_withdrawn = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Total cash withdrawals made"
    )
    total_spent = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Total store credit used"
    )
    
    # User activity metrics for revenue sharing calculation
    activity_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('1.00'),
        help_text="User activity score (1.00-5.00) affecting revenue share rate"
    )
    
    # Wallet preferences
    min_cashout_amount = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=Decimal('10.00'),
        help_text="Minimum amount for cash withdrawal"
    )
    
    # Legacy wallet field (deprecated in favor of available_balance)
    wallet = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    def __str__(self):
        return f"Profile for {self.user.email}"
    
    @property
    def total_balance(self):
        """Total balance including pending"""
        return self.available_balance + self.pending_balance
    
    @property
    def revenue_share_rate(self):
        """Calculate revenue share rate based on activity score (15-20%)"""
        base_rate = Decimal('0.15')  # 15% base rate
        bonus_rate = Decimal('0.05')  # Up to 5% bonus
        max_score = Decimal('5.00')
        
        # Calculate bonus based on activity score
        bonus = (self.activity_score - Decimal('1.00')) / (max_score - Decimal('1.00')) * bonus_rate
        return base_rate + bonus
    
    def can_withdraw(self, amount):
        """Check if user can withdraw specified amount"""
        return (
            amount >= self.min_cashout_amount and
            amount <= self.available_balance
        )


class WalletTransaction(models.Model):
    """Track all wallet transactions for audit trail and reconciliation"""
    
    TRANSACTION_TYPES = [
        ('EARNING_PROJECTED', 'Projected Earning'),
        ('EARNING_CONFIRMED', 'Confirmed Earning'),
        ('EARNING_ADJUSTED', 'Earning Adjustment'),
        ('SPENDING_STORE', 'Store Credit Usage'),
        ('WITHDRAWAL_CASH', 'Cash Withdrawal'),
        ('WITHDRAWAL_PENDING', 'Pending Withdrawal'),
        ('WITHDRAWAL_FAILED', 'Failed Withdrawal'),
        ('BONUS_ACTIVITY', 'Activity Bonus'),
        ('RECONCILIATION', 'Monthly Reconciliation'),
    ]
    
    STATUSES = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('FAILED', 'Failed'),
        ('REVERSED', 'Reversed'),
        ('PROCESSING', 'Processing'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallet_transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    status = models.CharField(max_length=15, choices=STATUSES, default='PENDING')
    
    # Amount details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    # Balance tracking
    balance_before = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Reference tracking
    affiliate_link = models.ForeignKey(
        'affiliates.AffiliateLink', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Affiliate link that generated this earning"
    )
    order_reference = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Order ID if this was store credit usage"
    )
    withdrawal_reference = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Payment processor reference (Stripe, PayPal, etc.)"
    )
    
    # Additional data
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Processing details
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='processed_transactions',
        help_text="Admin user who processed this transaction"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'transaction_type']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['affiliate_link']),
            models.Index(fields=['transaction_type', 'status']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.transaction_type} - ${self.amount}"
    
    def confirm_transaction(self):
        """Mark transaction as confirmed and update user balance"""
        if self.status != 'PENDING':
            raise ValueError(f"Can only confirm pending transactions, current status: {self.status}")
        
        self.status = 'CONFIRMED'
        self.processed_at = timezone.now()
        self.save()
        
        # Update user profile balance based on transaction type
        profile = self.user.profile
        
        if self.transaction_type in ['EARNING_PROJECTED', 'EARNING_CONFIRMED']:
            if self.transaction_type == 'EARNING_PROJECTED':
                profile.pending_balance += self.amount
            else:
                profile.available_balance += self.amount
                profile.lifetime_earnings += self.amount
                
        elif self.transaction_type == 'SPENDING_STORE':
            profile.available_balance -= self.amount
            profile.total_spent += self.amount
            
        elif self.transaction_type in ['WITHDRAWAL_CASH', 'WITHDRAWAL_PENDING']:
            profile.available_balance -= self.amount
            profile.total_withdrawn += self.amount
        
        profile.save()
        
        # Send notification about balance change
        from django.core.mail import send_mail
        from django.conf import settings
        
        if self.transaction_type == 'EARNING_CONFIRMED':
            send_mail(
                subject='Earnings Added to Your Wallet',
                message=f'${self.amount} has been added to your wallet. New balance: ${profile.available_balance}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.user.email],
                fail_silently=True
            )


class PayoutRequest(models.Model):
    """Track payout requests from users for admin approval and processing"""
    
    PAYOUT_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    ]
    
    PAYOUT_METHOD_CHOICES = [
        ('stripe_bank', 'Stripe Bank Transfer'),
        ('paypal', 'PayPal'),
        ('check', 'Paper Check'),
        ('other', 'Other'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    # Core request information
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='payout_requests',
        help_text="User requesting the payout"
    )
    
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Amount requested for payout"
    )
    
    status = models.CharField(
        max_length=20,
        choices=PAYOUT_STATUS_CHOICES,
        default='pending',
        help_text="Current status of the payout request"
    )
    
    # Payout method and details
    payout_method = models.CharField(
        max_length=20,
        choices=PAYOUT_METHOD_CHOICES,
        help_text="Method for delivering the payout"
    )
    
    # Recipient details (copied from user profile at time of request)
    recipient_email = models.EmailField(
        help_text="Email for PayPal or notifications"
    )
    
    stripe_connect_account_id = models.CharField(
        max_length=128, 
        blank=True, 
        null=True,
        help_text="Stripe Connect account ID (if using Stripe)"
    )
    
    paypal_email = models.EmailField(
        blank=True, 
        null=True,
        help_text="PayPal email (if using PayPal)"
    )
    
    # Request metadata
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='normal',
        help_text="Priority level for processing"
    )
    
    requested_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the payout was requested"
    )
    
    # Processing information
    approved_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the payout was approved"
    )
    
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payouts',
        help_text="Admin user who approved the payout"
    )
    
    processed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the payout was actually processed"
    )
    
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_payouts',
        help_text="Admin user who processed the payout"
    )
    
    completed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the payout was confirmed completed"
    )
    
    # External tracking
    external_transaction_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Transaction ID from payment processor (Stripe, PayPal, etc.)"
    )
    
    external_reference = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Reference number from payment processor"
    )
    
    # Fees and final amounts
    processing_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Fee charged by payment processor"
    )
    
    net_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Final amount received by user (after fees)"
    )
    
    # Notes and communication
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes for admin team"
    )
    
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if applicable)"
    )
    
    user_notes = models.TextField(
        blank=True,
        help_text="Notes from the user with their request"
    )
    
    # Retry and error handling
    retry_count = models.IntegerField(
        default=0,
        help_text="Number of processing attempts"
    )
    
    last_error = models.TextField(
        blank=True,
        help_text="Last error message if processing failed"
    )
    
    # Automatic retry settings
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When to retry processing (if failed)"
    )
    
    max_retries = models.IntegerField(
        default=3,
        help_text="Maximum number of retry attempts"
    )
    
    # Linked wallet transaction
    wallet_transaction = models.OneToOneField(
        WalletTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payout_request',
        help_text="Associated wallet transaction for this payout"
    )
    
    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata about the payout request"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['status', 'requested_at']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['payout_method', 'status']),
            models.Index(fields=['priority', 'requested_at']),
            models.Index(fields=['approved_at']),
            models.Index(fields=['processed_at']),
        ]
        
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='positive_payout_amount'
            ),
            models.CheckConstraint(
                check=models.Q(processing_fee__gte=0),
                name='non_negative_processing_fee'
            ),
        ]
    
    def __str__(self):
        return f"Payout Request #{self.id} - {self.user.email} - ${self.amount} ({self.status})"
    
    @property
    def is_pending(self):
        """Check if payout is pending admin action"""
        return self.status == 'pending'
    
    @property
    def is_approved(self):
        """Check if payout has been approved"""
        return self.status in ['approved', 'processing', 'completed']
    
    @property
    def is_completed(self):
        """Check if payout has been completed"""
        return self.status == 'completed'
    
    @property
    def is_failed(self):
        """Check if payout has failed"""
        return self.status == 'failed'
    
    @property
    def can_retry(self):
        """Check if payout can be retried"""
        return (
            self.status == 'failed' and 
            self.retry_count < self.max_retries and
            (self.next_retry_at is None or self.next_retry_at <= timezone.now())
        )
    
    @property
    def days_pending(self):
        """Number of days since request was made"""
        return (timezone.now() - self.requested_at).days
    
    @property
    def processing_time(self):
        """Time taken from approval to completion"""
        if self.approved_at and self.completed_at:
            return self.completed_at - self.approved_at
        return None
    
    def approve(self, admin_user, notes=""):
        """Approve the payout request"""
        if self.status != 'pending':
            raise ValueError(f"Cannot approve payout with status: {self.status}")
        
        self.status = 'approved'
        self.approved_at = timezone.now()
        self.approved_by = admin_user
        if notes:
            self.admin_notes = notes
        self.save()
        
        # Create wallet transaction for the withdrawal
        self.create_wallet_transaction()
    
    def reject(self, admin_user, reason):
        """Reject the payout request"""
        if self.status != 'pending':
            raise ValueError(f"Cannot reject payout with status: {self.status}")
        
        self.status = 'rejected'
        self.rejection_reason = reason
        self.processed_by = admin_user
        self.processed_at = timezone.now()
        self.save()
    
    def mark_processing(self, admin_user=None):
        """Mark payout as being processed"""
        if self.status != 'approved':
            raise ValueError(f"Cannot process payout with status: {self.status}")
        
        self.status = 'processing'
        self.processed_at = timezone.now()
        if admin_user:
            self.processed_by = admin_user
        self.save()
    
    def mark_completed(self, external_transaction_id=None, net_amount=None, processing_fee=None):
        """Mark payout as completed"""
        if self.status != 'processing':
            raise ValueError(f"Cannot complete payout with status: {self.status}")
        
        self.status = 'completed'
        self.completed_at = timezone.now()
        
        if external_transaction_id:
            self.external_transaction_id = external_transaction_id
        
        if net_amount is not None:
            self.net_amount = Decimal(str(net_amount))
        
        if processing_fee is not None:
            self.processing_fee = Decimal(str(processing_fee))
        
        self.save()
        
        # Update wallet transaction status
        if self.wallet_transaction:
            self.wallet_transaction.status = 'CONFIRMED'
            self.wallet_transaction.processed_at = timezone.now()
            self.wallet_transaction.withdrawal_reference = self.external_transaction_id
            self.wallet_transaction.save()
    
    def mark_failed(self, error_message, can_retry=True):
        """Mark payout as failed"""
        self.status = 'failed'
        self.last_error = error_message
        self.retry_count += 1
        
        if can_retry and self.retry_count < self.max_retries:
            # Schedule retry in 1 hour, then 24 hours, then 7 days
            retry_delays = [1, 24, 168]  # hours
            delay_hours = retry_delays[min(self.retry_count - 1, len(retry_delays) - 1)]
            self.next_retry_at = timezone.now() + timedelta(hours=delay_hours)
        
        self.save()
    
    def create_wallet_transaction(self):
        """Create associated wallet transaction for withdrawal"""
        if self.wallet_transaction:
            return self.wallet_transaction
        
        # Create withdrawal transaction
        transaction = WalletTransaction.objects.create(
            user=self.user,
            transaction_type='WITHDRAWAL_PENDING',
            status='PENDING',
            amount=self.amount,
            balance_before=self.user.profile.available_balance,
            balance_after=self.user.profile.available_balance - self.amount,
            description=f"Payout request #{self.id} via {self.get_payout_method_display()}",
            metadata={
                'payout_request_id': self.id,
                'payout_method': self.payout_method,
                'requested_at': self.requested_at.isoformat(),
            }
        )
        
        # Update user's available balance
        self.user.profile.available_balance -= self.amount
        self.user.profile.save(update_fields=['available_balance'])
        
        # Link to this payout request
        self.wallet_transaction = transaction
        self.save(update_fields=['wallet_transaction'])
        
        return transaction
    
    @classmethod
    def create_from_user_request(cls, user, amount, payout_method=None, user_notes=""):
        """Create a new payout request from user profile"""
        profile = user.profile
        
        # Validate user can request this payout
        if amount > profile.available_balance:
            raise ValueError("Insufficient available balance")
        
        if amount < profile.min_cashout_amount:
            raise ValueError(f"Amount below minimum cashout of ${profile.min_cashout_amount}")
        
        if profile.payout_status != 'eligible':
            raise ValueError("User not eligible for payouts")
        
        # Use user's preferred method if not specified
        if not payout_method:
            payout_method = profile.preferred_payout_method
        
        # Create the payout request
        payout_request = cls.objects.create(
            user=user,
            amount=amount,
            payout_method=payout_method,
            recipient_email=user.email,
            stripe_connect_account_id=profile.stripe_connect_account_id,
            paypal_email=profile.paypal_email,
            user_notes=user_notes,
            metadata={
                'user_activity_score': float(profile.activity_score),
                'user_lifetime_earnings': float(profile.lifetime_earnings),
                'request_source': 'user_dashboard',
            }
        )
        
        return payout_request