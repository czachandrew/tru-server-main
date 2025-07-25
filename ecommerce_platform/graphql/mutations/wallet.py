import graphene
from decimal import Decimal
from django.utils import timezone
from typing import Dict, Any

from users.models import User, UserProfile, WalletTransaction
from users.services import WalletService
from users.activity_metrics import ActivityMetricsService
from users.withdrawal_service import WithdrawalService, WithdrawalAdminService
from ..types.wallet import (
    WithdrawalRequestType, WalletTransactionType, ActivityMetricsType,
    WithdrawalRequestInput, StoreCreditsUsageInput, ActivityUpdateInput
)


class RequestWithdrawal(graphene.Mutation):
    """Mutation to request a cash withdrawal"""
    
    class Arguments:
        withdrawal_request = WithdrawalRequestInput(required=True)
    
    withdrawal_result = graphene.Field(WithdrawalRequestType)
    
    def mutate(self, info, withdrawal_request):
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            # Parse amount
            amount = Decimal(withdrawal_request.amount)
            method = withdrawal_request.method
            
            # Prepare payment details
            payment_details = {}
            
            if method == 'stripe':
                if not withdrawal_request.stripe_account_id:
                    raise ValueError("Stripe account ID required")
                payment_details['stripe_account_id'] = withdrawal_request.stripe_account_id
            
            elif method == 'paypal':
                if not withdrawal_request.paypal_email:
                    raise ValueError("PayPal email required")
                payment_details['paypal_email'] = withdrawal_request.paypal_email
            
            elif method == 'bank_transfer':
                required_fields = ['account_number', 'routing_number', 'bank_name', 'account_holder']
                for field in required_fields:
                    if not getattr(withdrawal_request, field):
                        raise ValueError(f"{field} is required for bank transfer")
                
                payment_details.update({
                    'account_number': withdrawal_request.account_number,
                    'routing_number': withdrawal_request.routing_number,
                    'bank_name': withdrawal_request.bank_name,
                    'account_holder': withdrawal_request.account_holder
                })
            
            elif method == 'check':
                required_fields = ['name', 'address1', 'city', 'state', 'zip_code']
                for field in required_fields:
                    if not getattr(withdrawal_request, field):
                        raise ValueError(f"{field} is required for check")
                
                payment_details.update({
                    'name': withdrawal_request.name,
                    'address1': withdrawal_request.address1,
                    'address2': withdrawal_request.address2 or '',
                    'city': withdrawal_request.city,
                    'state': withdrawal_request.state,
                    'zip_code': withdrawal_request.zip_code,
                    'country': withdrawal_request.country or 'US'
                })
            
            # Process withdrawal
            result = WithdrawalService.initiate_withdrawal(user, amount, method, payment_details)
            
            if result['success']:
                withdrawal_result = WithdrawalRequestType(
                    success=True,
                    transaction_id=result['transaction_id'],
                    method=result['method'],
                    amount=str(result['amount']),
                    fee=str(result['fee']),
                    total_amount=str(result['total_amount']),
                    estimated_completion=result['processing_result'].get('estimated_completion', 'Unknown'),
                    error_message=None
                )
            else:
                withdrawal_result = WithdrawalRequestType(
                    success=False,
                    error_message=result['error']
                )
            
            return RequestWithdrawal(withdrawal_result=withdrawal_result)
            
        except Exception as e:
            return RequestWithdrawal(
                withdrawal_result=WithdrawalRequestType(
                    success=False,
                    error_message=str(e)
                )
            )


class CancelWithdrawal(graphene.Mutation):
    """Mutation to cancel a pending withdrawal"""
    
    class Arguments:
        transaction_id = graphene.Int(required=True)
        reason = graphene.String(default_value="User request")
    
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, transaction_id, reason):
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            # Verify user owns this transaction
            transaction = WalletTransaction.objects.get(id=transaction_id)
            if transaction.user != user:
                raise Exception("Access denied")
            
            result = WithdrawalService.cancel_withdrawal(transaction_id, reason)
            
            return CancelWithdrawal(
                success=result['success'],
                message=f"Withdrawal cancelled: {result['reason']}"
            )
            
        except Exception as e:
            return CancelWithdrawal(
                success=False,
                message=str(e)
            )


class UseStoreCredit(graphene.Mutation):
    """Mutation to use store credit for a purchase"""
    
    class Arguments:
        store_credit_request = StoreCreditsUsageInput(required=True)
    
    transaction = graphene.Field(WalletTransactionType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, store_credit_request):
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            amount = Decimal(store_credit_request.amount)
            order_reference = store_credit_request.order_reference
            
            # Process store credit usage
            transaction = WalletService.process_store_credit_usage(user, amount, order_reference)
            
            return UseStoreCredit(
                transaction=transaction,
                success=True,
                message=f"Store credit of ${amount} applied to order {order_reference}"
            )
            
        except Exception as e:
            return UseStoreCredit(
                transaction=None,
                success=False,
                message=str(e)
            )


class UpdateActivityScore(graphene.Mutation):
    """Mutation to update user activity score"""
    
    class Arguments:
        activity_data = ActivityUpdateInput(required=True)
    
    activity_metrics = graphene.Field(ActivityMetricsType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, activity_data):
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            # Prepare activity data
            activity_dict = {}
            if activity_data.affiliate_clicks is not None:
                activity_dict['affiliate_clicks'] = activity_data.affiliate_clicks
            if activity_data.successful_conversions is not None:
                activity_dict['successful_conversions'] = activity_data.successful_conversions
            if activity_data.days_active is not None:
                activity_dict['days_active'] = activity_data.days_active
            if activity_data.search_queries is not None:
                activity_dict['search_queries'] = activity_data.search_queries
            if activity_data.referrals_made is not None:
                activity_dict['referrals_made'] = activity_data.referrals_made
            
            # Update activity score
            result = ActivityMetricsService.update_user_activity_score(user, activity_data.force_update)
            
            if result['updated']:
                # Get updated metrics
                metrics = ActivityMetricsService.calculate_user_activity_score(user)
                
                activity_metrics = ActivityMetricsType(
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
                
                message = f"Activity score updated: {result['old_score']} → {result['new_score']}"
            else:
                activity_metrics = None
                message = f"Activity score not updated: {result['reason']}"
            
            return UpdateActivityScore(
                activity_metrics=activity_metrics,
                success=result['updated'],
                message=message
            )
            
        except Exception as e:
            return UpdateActivityScore(
                activity_metrics=None,
                success=False,
                message=str(e)
            )


class CreateProjectedEarning(graphene.Mutation):
    """Mutation to create projected earning (for affiliate actions)"""
    
    class Arguments:
        affiliate_link_id = graphene.Int(required=True)
        estimated_revenue = graphene.String(required=True)
    
    transaction = graphene.Field(WalletTransactionType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, affiliate_link_id, estimated_revenue):
        user = info.context.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        try:
            from affiliates.models import AffiliateLink
            
            # Get affiliate link
            affiliate_link = AffiliateLink.objects.get(id=affiliate_link_id)
            estimated_revenue_decimal = Decimal(estimated_revenue)
            
            # Create projected earning
            transaction = WalletService.create_projected_earning(
                user, affiliate_link, estimated_revenue_decimal
            )
            
            return CreateProjectedEarning(
                transaction=transaction,
                success=True,
                message=f"Projected earning created: ${transaction.amount}"
            )
            
        except Exception as e:
            return CreateProjectedEarning(
                transaction=None,
                success=False,
                message=str(e)
            )


# Admin mutations
class ApproveWithdrawal(graphene.Mutation):
    """Admin mutation to approve a pending withdrawal"""
    
    class Arguments:
        transaction_id = graphene.Int(required=True)
    
    success = graphene.Boolean()
    message = graphene.String()
    reference = graphene.String()
    
    def mutate(self, info, transaction_id):
        user = info.context.user
        if not user.is_authenticated or not user.is_staff:
            raise Exception("Admin access required")
        
        try:
            result = WithdrawalAdminService.approve_withdrawal(transaction_id, user)
            
            return ApproveWithdrawal(
                success=result['success'],
                message=f"Withdrawal approved by {result['approved_by']}",
                reference=result['reference']
            )
            
        except Exception as e:
            return ApproveWithdrawal(
                success=False,
                message=str(e),
                reference=None
            )


class RejectWithdrawal(graphene.Mutation):
    """Admin mutation to reject a pending withdrawal"""
    
    class Arguments:
        transaction_id = graphene.Int(required=True)
        reason = graphene.String(required=True)
    
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, transaction_id, reason):
        user = info.context.user
        if not user.is_authenticated or not user.is_staff:
            raise Exception("Admin access required")
        
        try:
            result = WithdrawalAdminService.reject_withdrawal(transaction_id, user, reason)
            
            return RejectWithdrawal(
                success=result['success'],
                message=f"Withdrawal rejected by {result['rejected_by']}: {result['reason']}"
            )
            
        except Exception as e:
            return RejectWithdrawal(
                success=False,
                message=str(e)
            )


class ConfirmEarning(graphene.Mutation):
    """Admin mutation to confirm projected earnings with actual revenue"""
    
    class Arguments:
        projected_transaction_id = graphene.Int(required=True)
        actual_revenue = graphene.String(required=True)
    
    confirmed_transaction = graphene.Field(WalletTransactionType)
    success = graphene.Boolean()
    message = graphene.String()
    
    def mutate(self, info, projected_transaction_id, actual_revenue):
        user = info.context.user
        if not user.is_authenticated or not user.is_staff:
            raise Exception("Admin access required")
        
        try:
            # Get projected transaction
            projected_transaction = WalletTransaction.objects.get(id=projected_transaction_id)
            actual_revenue_decimal = Decimal(actual_revenue)
            
            # Confirm earning
            confirmed_transaction = WalletService.confirm_earning(
                projected_transaction, actual_revenue_decimal
            )
            
            return ConfirmEarning(
                confirmed_transaction=confirmed_transaction,
                success=True,
                message=f"Earning confirmed: ${confirmed_transaction.amount}"
            )
            
        except Exception as e:
            return ConfirmEarning(
                confirmed_transaction=None,
                success=False,
                message=str(e)
            )


class WalletMutations(graphene.ObjectType):
    """GraphQL mutations for wallet operations"""
    
    # User mutations
    request_withdrawal = RequestWithdrawal.Field()
    cancel_withdrawal = CancelWithdrawal.Field()
    use_store_credit = UseStoreCredit.Field()
    update_activity_score = UpdateActivityScore.Field()
    create_projected_earning = CreateProjectedEarning.Field()
    
    # Admin mutations
    approve_withdrawal = ApproveWithdrawal.Field()
    reject_withdrawal = RejectWithdrawal.Field()
    confirm_earning = ConfirmEarning.Field() 