# Demo-Friendly Wallet Strategy

## 🎯 **Current Issue**
- Extension calls `trackPurchaseIntent` with VERY_HIGH confidence
- Should create projected earnings, but no click event exists
- Need demo-friendly approach that doesn't create runaway projected balances

## 💡 **Proposed Solution: Smart Projection Management**

### **1. Auto-Create Missing Click Events (Demo Mode)**
For demo purposes, if a purchase intent arrives without a click event, create one automatically:

```python
# In TrackPurchaseIntent.mutate method
if not click_event and settings.DEBUG:  # Only in development/demo
    # Extract affiliate info from the URL
    affiliate_link = self.extract_affiliate_from_url(input.page_url)
    
    if affiliate_link:
        # Create the missing click event
        click_event = AffiliateClickEvent.objects.create(
            user=info.context.user,
            affiliate_link=affiliate_link,
            session_id=input.click_event_id,
            source='auto_created_demo',
            target_domain=urlparse(input.page_url).netloc,
            product_data={'auto_created': True, 'demo_mode': True}
        )
```

### **2. Projected Earnings Caps & Limits**
```python
# Enhanced projection logic with safeguards
def create_projected_earning(self):
    # Check daily projection limit per user
    today = timezone.now().date()
    daily_projections = WalletTransaction.objects.filter(
        user=self.user,
        transaction_type='EARNING_PROJECTED',
        created_at__date=today
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Cap daily projections at $50 for demos
    DAILY_PROJECTION_CAP = Decimal('50.00')
    if daily_projections >= DAILY_PROJECTION_CAP:
        return None  # Don't create more projections today
    
    projected_amount = self.calculate_projected_commission()
    
    # Cap individual projections at $10
    MAX_SINGLE_PROJECTION = Decimal('10.00')
    projected_amount = min(projected_amount, MAX_SINGLE_PROJECTION)
    
    # Ensure we don't exceed daily cap
    if daily_projections + projected_amount > DAILY_PROJECTION_CAP:
        projected_amount = DAILY_PROJECTION_CAP - daily_projections
    
    # Create transaction with demo metadata
    transaction = WalletTransaction.objects.create(
        user=self.user,
        transaction_type='EARNING_PROJECTED',
        amount=projected_amount,
        balance_before=self.user.profile.pending_balance,
        balance_after=self.user.profile.pending_balance + projected_amount,
        affiliate_link=self.affiliate_link,
        description=f"Demo projection: {self.intent_stage} on {self.affiliate_link.platform}",
        metadata={
            'is_demo': True,
            'daily_cap_applied': daily_projections + projected_amount >= DAILY_PROJECTION_CAP,
            'original_amount': float(self.calculate_projected_commission()),
            'capped_amount': float(projected_amount),
            # ... existing metadata
        }
    )
    
    return transaction
```

### **3. Auto-Cleanup Stale Projections**
```python
# Management command: python manage.py cleanup_demo_projections
def cleanup_old_projections():
    # Remove projections older than 7 days
    cutoff_date = timezone.now() - timedelta(days=7)
    
    old_projections = WalletTransaction.objects.filter(
        transaction_type='EARNING_PROJECTED',
        created_at__lt=cutoff_date,
        metadata__is_demo=True
    )
    
    for txn in old_projections:
        # Reverse the pending balance
        txn.user.profile.pending_balance -= txn.amount
        txn.user.profile.save(update_fields=['pending_balance'])
        
        # Delete the transaction
        txn.delete()
```

### **4. Demo Reset Function**
```python
# Quick reset for demos
def reset_user_demo_wallet(user):
    # Remove all demo projections
    demo_projections = WalletTransaction.objects.filter(
        user=user,
        transaction_type='EARNING_PROJECTED',
        metadata__is_demo=True
    )
    
    total_to_remove = demo_projections.aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    # Reset pending balance
    user.profile.pending_balance -= total_to_remove
    user.profile.save(update_fields=['pending_balance'])
    
    # Delete demo projections
    demo_projections.delete()
    
    return f"Removed ${total_to_remove} in demo projections"
```

## 🎮 **Demo Scenarios**

### **Scenario 1: Clean Demo**
```python
# Start fresh for each demo
reset_user_demo_wallet(demo_user)
```

### **Scenario 2: Progressive Demo**
```python
# Show building wallet over time
# Day 1: $5.50 projection (Amazon headphones)
# Day 2: $12.30 projection (Best Buy laptop)
# Day 3: $8.75 projection (Target home goods)
# Total: $26.55 pending (realistic demo amount)
```

### **Scenario 3: Conversion Demo**
```python
# Show projection → confirmation flow
# 1. Create projection ($15.00 pending)
# 2. Simulate monthly reconciliation
# 3. Move to available balance ($15.00 available)
```

## ⚙️ **Implementation Strategy**

### **Phase 1: Quick Fix (Immediate)**
Add auto-creation of click events in development mode:

```python
# In ecommerce_platform/graphql/mutations/affiliate.py
def extract_affiliate_from_url(self, url):
    """Extract affiliate information from URL for auto-creation"""
    if 'amazon.com' in url and 'tag=' in url:
        # Extract Amazon affiliate tag
        tag_match = re.search(r'tag=([^&]+)', url)
        if tag_match:
            tag = tag_match.group(1)
            # Find or create affiliate link for this tag
            # Return the AffiliateLink object
    return None
```

### **Phase 2: Enhanced Controls**
- Add daily/weekly projection caps
- Implement auto-cleanup
- Add demo reset functionality

### **Phase 3: Smart Projections**
- Machine learning confidence scoring
- Historical conversion rate analysis
- Platform-specific projection logic

## 🎯 **Benefits for Demos**

1. **✅ Immediate Wallet Updates** - Users see instant feedback
2. **✅ Controlled Growth** - Caps prevent runaway balances  
3. **✅ Easy Reset** - Quick cleanup between demos
4. **✅ Realistic Amounts** - $5-15 projections feel authentic
5. **✅ Progressive Building** - Show accumulation over time

## 🚀 **Next Steps**

1. **Immediate**: Add auto-click-creation for missing events
2. **Short-term**: Implement projection caps and limits
3. **Long-term**: Build comprehensive demo management system

This approach gives you **immediate demo functionality** while **preventing runaway projections**! 🎯 