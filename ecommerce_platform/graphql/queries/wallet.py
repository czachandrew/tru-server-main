import graphene
from graphene_django import DjangoObjectType
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from typing import List, Dict, Any

from users.models import User, UserProfile, WalletTransaction
from users.services import WalletService
from users.activity_metrics import ActivityMetricsService
from users.withdrawal_service import WithdrawalService
from ..types.wallet import (
    WalletBalanceType, WalletTransactionType, WalletSummaryType,
    WithdrawalMethodType, ActivityMetricsType, LeaderboardEntryType,
    ReconciliationResultType
)


class WalletQueries(graphene.ObjectType):
    """GraphQL queries for wallet operations"""
    
    # Balance queries
    wallet_balance = graphene.Field(
        WalletBalanceType,
        description="Get current wallet balance for authenticated user"
    )
    
    # Transaction queries
    wallet_transactions = graphene.List(
        WalletTransactionType,
        limit=graphene.Int(default_value=20),
        offset=graphene.Int(default_value=0),
        transaction_type=graphene.String(),
        status=graphene.String(),
        description="Get wallet transactions for authenticated user"
    )
    
    wallet_transaction = graphene.Field(
        WalletTransactionType,
        transaction_id=graphene.Int(required=True),
        description="Get specific wallet transaction by ID"
    )
    
    # Summary queries
    wallet_summary = graphene.Field(
        WalletSummaryType,
        description="Get comprehensive wallet summary for authenticated user"
    )
    
    # Withdrawal queries
    withdrawal_methods = graphene.List(
        WithdrawalMethodType,
        description="Get available withdrawal methods for authenticated user"
    )
    
    withdrawal_status = graphene.Field(
        graphene.String,
        transaction_id=graphene.Int(required=True),
        description="Get withdrawal status by transaction ID"
    )
    
    # Activity queries
    activity_metrics = graphene.Field(
        ActivityMetricsType,
        days_back=graphene.Int(default_value=30),
        description="Get user activity metrics for authenticated user"
    )
    
    activity_leaderboard = graphene.List(
        LeaderboardEntryType,
        limit=graphene.Int(default_value=10),
        description="Get activity leaderboard (top users by activity score)"
    )
    
    # Admin queries
    all_transactions = graphene.List(
        WalletTransactionType,
        limit=graphene.Int(default_value=50),
        offset=graphene.Int(default_value=0),
        user_email=graphene.String(),
        transaction_type=graphene.String(),
        status=graphene.String(),
        description="Get all wallet transactions (admin only)"
    )
    
    pending_withdrawals = graphene.List(
        WalletTransactionType,
        description="Get pending withdrawals (admin only)"
    )
    
    # Resolvers
    def resolve_wallet_balance(self, info):
        """Get wallet balance for authenticated user"""
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            profile = user.profile
            return WalletBalanceType(
                available_balance=str(profile.available_balance),
                pending_balance=str(profile.pending_balance),
                total_balance=str(profile.total_balance),
                lifetime_earnings=str(profile.lifetime_earnings),
                total_withdrawn=str(profile.total_withdrawn),
                total_spent=str(profile.total_spent),
                activity_score=str(profile.activity_score),
                revenue_share_rate=str(profile.revenue_share_rate),
                can_withdraw=profile.can_withdraw(profile.min_cashout_amount),
                min_cashout_amount=str(profile.min_cashout_amount)
            )
        except Exception as e:
            raise Exception(f"Error fetching wallet balance: {str(e)}")
    
    def resolve_wallet_transactions(self, info, limit=20, offset=0, transaction_type=None, status=None):
        """Get wallet transactions for authenticated user"""
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            queryset = WalletTransaction.objects.filter(user=user)
            
            # Apply filters
            if transaction_type:
                queryset = queryset.filter(transaction_type=transaction_type)
            if status:
                queryset = queryset.filter(status=status)
            
            # Apply pagination
            queryset = queryset.order_by('-created_at')[offset:offset + limit]
            
            return queryset
        except Exception as e:
            raise Exception(f"Error fetching wallet transactions: {str(e)}")
    
    def resolve_wallet_transaction(self, info, transaction_id):
        """Get specific wallet transaction by ID"""
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            transaction = WalletTransaction.objects.get(id=transaction_id, user=user)
            return transaction
        except WalletTransaction.DoesNotExist:
            raise Exception("Transaction not found")
    
    def resolve_wallet_summary(self, info):
        """Get comprehensive wallet summary"""
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            summary = WalletService.get_wallet_summary(user)
            
            # Convert to GraphQL types
            balance = WalletBalanceType(
                available_balance=str(summary['available_balance']),
                pending_balance=str(summary['pending_balance']),
                total_balance=str(summary['total_balance']),
                lifetime_earnings=str(summary['lifetime_earnings']),
                total_withdrawn=str(summary['total_withdrawn']),
                total_spent=str(summary['total_spent']),
                activity_score=str(summary['activity_score']),
                revenue_share_rate=str(summary['revenue_share_rate']),
                can_withdraw=summary['can_withdraw'],
                min_cashout_amount=str(summary['min_cashout_amount'])
            )
            
            # Get withdrawal methods
            withdrawal_methods = WithdrawalService.get_available_methods(user)
            withdrawal_method_types = []
            for method_code, method_data in withdrawal_methods.items():
                withdrawal_method_types.append(WithdrawalMethodType(
                    method_code=method_code,
                    name=method_data['name'],
                    min_amount=str(method_data['min_amount']),
                    fee=str(method_data['fee']),
                    available=method_data['available'],
                    processing_time=method_data['processing_time']
                ))
            
            # Get activity metrics
            activity_data = ActivityMetricsService.get_user_activity_summary(user)
            current_metrics = activity_data['current_metrics']
            
            activity_metrics = ActivityMetricsType(
                raw_score=str(current_metrics['raw_score']),
                normalized_score=str(current_metrics['normalized_score']),
                revenue_share_rate=str(current_metrics['revenue_share_rate']),
                period_days=current_metrics['period_days'],
                affiliate_clicks=current_metrics['metrics']['affiliate_clicks'],
                successful_conversions=current_metrics['metrics']['successful_conversions'],
                days_active=current_metrics['metrics']['days_active'],
                search_queries=current_metrics['metrics']['search_queries'],
                referrals_made=current_metrics['metrics']['referrals_made'],
                consecutive_days=current_metrics['metrics']['consecutive_days'],
                high_value_conversions=current_metrics['metrics']['high_value_conversions'],
                user_rank=activity_data['leaderboard_rank']
            )
            
            # Get transaction counts and dates
            total_transactions = WalletTransaction.objects.filter(user=user).count()
            
            last_earning = WalletTransaction.objects.filter(
                user=user,
                transaction_type='EARNING_CONFIRMED'
            ).order_by('-created_at').first()
            
            last_withdrawal = WalletTransaction.objects.filter(
                user=user,
                transaction_type='WITHDRAWAL_CASH'
            ).order_by('-created_at').first()
            
            return WalletSummaryType(
                balance=balance,
                recent_transactions=summary['recent_transactions'],
                pending_transactions=summary['pending_transactions'],
                withdrawal_methods=withdrawal_method_types,
                activity_metrics=activity_metrics,
                total_transactions=total_transactions,
                last_earning_date=last_earning.created_at if last_earning else None,
                last_withdrawal_date=last_withdrawal.created_at if last_withdrawal else None
            )
            
        except Exception as e:
            raise Exception(f"Error fetching wallet summary: {str(e)}")
    
    def resolve_withdrawal_methods(self, info):
        """Get available withdrawal methods"""
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            methods = WithdrawalService.get_available_methods(user)
            method_types = []
            
            for method_code, method_data in methods.items():
                method_types.append(WithdrawalMethodType(
                    method_code=method_code,
                    name=method_data['name'],
                    min_amount=str(method_data['min_amount']),
                    fee=str(method_data['fee']),
                    available=method_data['available'],
                    processing_time=method_data['processing_time']
                ))
            
            return method_types
        except Exception as e:
            raise Exception(f"Error fetching withdrawal methods: {str(e)}")
    
    def resolve_withdrawal_status(self, info, transaction_id):
        """Get withdrawal status"""
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            status = WithdrawalService.get_withdrawal_status(transaction_id)
            
            # Verify user owns this transaction
            transaction = WalletTransaction.objects.get(id=transaction_id)
            if transaction.user != user:
                raise Exception("Access denied")
            
            return status
        except Exception as e:
            raise Exception(f"Error fetching withdrawal status: {str(e)}")
    
    def resolve_activity_metrics(self, info, days_back=30):
        """Get user activity metrics"""
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            metrics = ActivityMetricsService.calculate_user_activity_score(user, days_back)
            
            return ActivityMetricsType(
                raw_score=str(metrics['raw_score']),
                normalized_score=str(metrics['normalized_score']),
                revenue_share_rate=str(metrics['revenue_share_rate']),
                period_days=metrics['period_days'],
                affiliate_clicks=metrics['metrics']['affiliate_clicks'],
                successful_conversions=metrics['metrics']['successful_conversions'],
                days_active=metrics['metrics']['days_active'],
                search_queries=metrics['metrics']['search_queries'],
                referrals_made=metrics['metrics']['referrals_made'],
                consecutive_days=metrics['metrics']['consecutive_days'],
                high_value_conversions=metrics['metrics']['high_value_conversions'],
                user_rank=ActivityMetricsService._get_user_rank(user)
            )
        except Exception as e:
            raise Exception(f"Error fetching activity metrics: {str(e)}")
    
    def resolve_activity_leaderboard(self, info, limit=10):
        """Get activity leaderboard"""
        try:
            leaderboard = ActivityMetricsService.get_activity_leaderboard(limit)
            
            leaderboard_entries = []
            for entry in leaderboard:
                leaderboard_entries.append(LeaderboardEntryType(
                    rank=entry['rank'],
                    user_email=entry['user'].email,
                    user_name=entry['user'].get_full_name() or entry['user'].email,
                    activity_score=str(entry['activity_score']),
                    revenue_share_rate=str(entry['revenue_share_rate']),
                    lifetime_earnings=str(entry['lifetime_earnings']),
                    available_balance=str(entry['available_balance'])
                ))
            
            return leaderboard_entries
        except Exception as e:
            raise Exception(f"Error fetching activity leaderboard: {str(e)}")
    
    def resolve_all_transactions(self, info, limit=50, offset=0, user_email=None, transaction_type=None, status=None):
        """Get all wallet transactions (admin only)"""
        user = info.context.user
        if not user.is_authenticated or not user.is_staff:
            raise Exception("Admin access required")
        
        try:
            queryset = WalletTransaction.objects.all()
            
            # Apply filters
            if user_email:
                queryset = queryset.filter(user__email__icontains=user_email)
            if transaction_type:
                queryset = queryset.filter(transaction_type=transaction_type)
            if status:
                queryset = queryset.filter(status=status)
            
            # Apply pagination
            queryset = queryset.select_related('user', 'affiliate_link').order_by('-created_at')[offset:offset + limit]
            
            return queryset
        except Exception as e:
            raise Exception(f"Error fetching all transactions: {str(e)}")
    
    def resolve_pending_withdrawals(self, info):
        """Get pending withdrawals (admin only)"""
        user = info.context.user
        if not user.is_authenticated or not user.is_staff:
            raise Exception("Admin access required")
        
        try:
            pending_withdrawals = WalletTransaction.objects.filter(
                transaction_type='WITHDRAWAL_PENDING',
                status='PENDING'
            ).select_related('user').order_by('-created_at')
            
            return pending_withdrawals
        except Exception as e:
            raise Exception(f"Error fetching pending withdrawals: {str(e)}") 