import graphene
from graphene_django import DjangoObjectType
from decimal import Decimal
from django.utils import timezone
from typing import List

from users.models import User, UserProfile, WalletTransaction


class WalletTransactionType(DjangoObjectType):
    """GraphQL type for wallet transactions"""
    
    class Meta:
        model = WalletTransaction
        fields = (
            'id', 'transaction_type', 'status', 'amount', 'currency',
            'balance_before', 'balance_after', 'description', 'created_at',
            'updated_at', 'processed_at', 'metadata'
        )
    
    # Add computed fields
    affiliate_platform = graphene.String()
    display_amount = graphene.String()
    is_earning = graphene.Boolean()
    is_withdrawal = graphene.Boolean()
    is_spending = graphene.Boolean()
    
    def resolve_affiliate_platform(self, info):
        """Get the affiliate platform if this transaction is related to an affiliate link"""
        if self.affiliate_link:
            return self.affiliate_link.platform
        return None
    
    def resolve_display_amount(self, info):
        """Get formatted amount for display"""
        return f"${self.amount:.2f}"
    
    def resolve_is_earning(self, info):
        """Check if this is an earning transaction"""
        return self.transaction_type in ['EARNING_PROJECTED', 'EARNING_CONFIRMED', 'BONUS_ACTIVITY']
    
    def resolve_is_withdrawal(self, info):
        """Check if this is a withdrawal transaction"""
        return self.transaction_type in ['WITHDRAWAL_CASH', 'WITHDRAWAL_PENDING', 'WITHDRAWAL_FAILED']
    
    def resolve_is_spending(self, info):
        """Check if this is a spending transaction"""
        return self.transaction_type == 'SPENDING_STORE'


class WalletBalanceType(graphene.ObjectType):
    """GraphQL type for wallet balance information"""
    
    available_balance = graphene.String()
    pending_balance = graphene.String()
    total_balance = graphene.String()
    lifetime_earnings = graphene.String()
    total_withdrawn = graphene.String()
    total_spent = graphene.String()
    
    # Activity metrics
    activity_score = graphene.String()
    revenue_share_rate = graphene.String()
    
    # Capabilities
    can_withdraw = graphene.Boolean()
    min_cashout_amount = graphene.String()
    
    # Display fields
    available_balance_display = graphene.String()
    pending_balance_display = graphene.String()
    total_balance_display = graphene.String()
    
    def resolve_available_balance_display(self, info):
        return f"${self.available_balance:.2f}"
    
    def resolve_pending_balance_display(self, info):
        return f"${self.pending_balance:.2f}"
    
    def resolve_total_balance_display(self, info):
        return f"${self.total_balance:.2f}"


class ActivityMetricsType(graphene.ObjectType):
    """GraphQL type for user activity metrics"""
    
    raw_score = graphene.String()
    normalized_score = graphene.String()
    revenue_share_rate = graphene.String()
    period_days = graphene.Int()
    
    # Individual metrics
    affiliate_clicks = graphene.Int()
    successful_conversions = graphene.Int()
    days_active = graphene.Int()
    search_queries = graphene.Int()
    referrals_made = graphene.Int()
    consecutive_days = graphene.Int()
    high_value_conversions = graphene.Int()
    
    # Leaderboard info
    user_rank = graphene.Int()
    next_threshold = graphene.Field('self')
    
    class NextThresholdType(graphene.ObjectType):
        next_score = graphene.String()
        next_rate = graphene.String()
        next_description = graphene.String()
        points_needed = graphene.String()


class WithdrawalMethodType(graphene.ObjectType):
    """GraphQL type for available withdrawal methods"""
    
    method_code = graphene.String()
    name = graphene.String()
    min_amount = graphene.String()
    fee = graphene.String()
    available = graphene.Boolean()
    processing_time = graphene.String()
    
    # Display fields
    min_amount_display = graphene.String()
    fee_display = graphene.String()
    
    def resolve_min_amount_display(self, info):
        return f"${self.min_amount:.2f}"
    
    def resolve_fee_display(self, info):
        return f"${self.fee:.2f}"


class WalletSummaryType(graphene.ObjectType):
    """GraphQL type for comprehensive wallet summary"""
    
    balance = graphene.Field(WalletBalanceType)
    recent_transactions = graphene.List(WalletTransactionType)
    pending_transactions = graphene.List(WalletTransactionType)
    withdrawal_methods = graphene.List(WithdrawalMethodType)
    activity_metrics = graphene.Field(ActivityMetricsType)
    
    # Quick stats
    total_transactions = graphene.Int()
    last_earning_date = graphene.DateTime()
    last_withdrawal_date = graphene.DateTime()


class WithdrawalRequestType(graphene.ObjectType):
    """GraphQL type for withdrawal request results"""
    
    success = graphene.Boolean()
    transaction_id = graphene.Int()
    method = graphene.String()
    amount = graphene.String()
    fee = graphene.String()
    total_amount = graphene.String()
    estimated_completion = graphene.String()
    error_message = graphene.String()
    
    # Display fields
    amount_display = graphene.String()
    fee_display = graphene.String()
    total_amount_display = graphene.String()
    
    def resolve_amount_display(self, info):
        return f"${self.amount:.2f}" if self.amount else None
    
    def resolve_fee_display(self, info):
        return f"${self.fee:.2f}" if self.fee else None
    
    def resolve_total_amount_display(self, info):
        return f"${self.total_amount:.2f}" if self.total_amount else None


class LeaderboardEntryType(graphene.ObjectType):
    """GraphQL type for activity leaderboard entries"""
    
    rank = graphene.Int()
    user_email = graphene.String()
    user_name = graphene.String()
    activity_score = graphene.String()
    revenue_share_rate = graphene.String()
    lifetime_earnings = graphene.String()
    available_balance = graphene.String()
    
    # Display fields
    activity_score_display = graphene.String()
    revenue_share_rate_display = graphene.String()
    lifetime_earnings_display = graphene.String()
    available_balance_display = graphene.String()
    
    def resolve_activity_score_display(self, info):
        return f"{self.activity_score:.2f}"
    
    def resolve_revenue_share_rate_display(self, info):
        return f"{float(self.revenue_share_rate) * 100:.1f}%"
    
    def resolve_lifetime_earnings_display(self, info):
        return f"${self.lifetime_earnings:.2f}"
    
    def resolve_available_balance_display(self, info):
        return f"${self.available_balance:.2f}"


class ReconciliationResultType(graphene.ObjectType):
    """GraphQL type for reconciliation results"""
    
    period = graphene.String()
    platform = graphene.String()
    processed_links = graphene.Int()
    total_users_affected = graphene.Int()
    total_projected = graphene.String()
    total_actual = graphene.String()
    total_adjustment = graphene.String()
    accuracy_percentage = graphene.Float()
    
    # Display fields
    total_projected_display = graphene.String()
    total_actual_display = graphene.String()
    total_adjustment_display = graphene.String()
    
    def resolve_total_projected_display(self, info):
        return f"${self.total_projected:.2f}"
    
    def resolve_total_actual_display(self, info):
        return f"${self.total_actual:.2f}"
    
    def resolve_total_adjustment_display(self, info):
        return f"${self.total_adjustment:.2f}"


# Input types for mutations
class WithdrawalRequestInput(graphene.InputObjectType):
    """Input type for withdrawal requests"""
    
    amount = graphene.String(required=True)
    method = graphene.String(required=True)
    
    # Payment method specific fields
    stripe_account_id = graphene.String()
    paypal_email = graphene.String()
    
    # Bank transfer fields
    account_number = graphene.String()
    routing_number = graphene.String()
    bank_name = graphene.String()
    account_holder = graphene.String()
    
    # Check mailing fields
    name = graphene.String()
    address1 = graphene.String()
    address2 = graphene.String()
    city = graphene.String()
    state = graphene.String()
    zip_code = graphene.String()
    country = graphene.String()


class StoreCreditsUsageInput(graphene.InputObjectType):
    """Input type for using store credits"""
    
    amount = graphene.String(required=True)
    order_reference = graphene.String(required=True)


class ActivityUpdateInput(graphene.InputObjectType):
    """Input type for activity updates"""
    
    affiliate_clicks = graphene.Int()
    successful_conversions = graphene.Int()
    days_active = graphene.Int()
    search_queries = graphene.Int()
    referrals_made = graphene.Int()
    force_update = graphene.Boolean(default_value=False) 