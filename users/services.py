"""
Wallet Services - Business logic for user wallet operations
"""

from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import User, UserProfile, WalletTransaction, PayoutRequest


class WalletService:
    """Service class for wallet-related operations"""
    
    @staticmethod
    def get_wallet_summary(user):
        """Get comprehensive wallet summary for a user"""
        profile = user.profile
        
        # Get recent transactions
        recent_transactions = WalletTransaction.objects.filter(
            user=user
        ).order_by('-created_at')[:10]
        
        # Get pending transactions
        pending_transactions = WalletTransaction.objects.filter(
            user=user,
            status='PENDING'
        ).order_by('-created_at')
        
        # Calculate total balance
        total_balance = profile.available_balance + profile.pending_balance
        
        # Check if user can withdraw
        can_withdraw = (
            profile.available_balance >= profile.min_cashout_amount and
            profile.payout_status == 'eligible'
        )
        
        return {
            'available_balance': profile.available_balance,
            'pending_balance': profile.pending_balance,
            'total_balance': total_balance,
            'lifetime_earnings': profile.lifetime_earnings,
            'total_withdrawn': profile.total_withdrawn,
            'can_withdraw': can_withdraw,
            'min_cashout_amount': profile.min_cashout_amount,
            'revenue_share_rate': profile.revenue_share_rate,
            'recent_transactions': recent_transactions,
            'pending_transactions': pending_transactions,
        }
    
    @staticmethod
    def confirm_earning(transaction, actual_revenue=None):
        """Confirm a projected earning and move it to available balance"""
        if transaction.transaction_type != 'EARNING_PROJECTED':
            raise ValueError("Can only confirm projected earnings")
        
        if transaction.status != 'PENDING':
            raise ValueError("Transaction must be pending to confirm")
        
        profile = transaction.user.profile
        
        # If actual revenue provided, recalculate user's share
        if actual_revenue is not None:
            actual_user_share = Decimal(str(actual_revenue)) * profile.revenue_share_rate
            # Update transaction amount if different
            if actual_user_share != transaction.amount:
                # Create adjustment transaction
                adjustment_amount = actual_user_share - transaction.amount
                WalletTransaction.objects.create(
                    user=transaction.user,
                    transaction_type='EARNING_ADJUSTED',
                    status='CONFIRMED',
                    amount=adjustment_amount,
                    balance_before=profile.pending_balance,
                    balance_after=profile.pending_balance + adjustment_amount,
                    description=f"Adjustment for transaction #{transaction.id}",
                    metadata={'original_transaction_id': transaction.id}
                )
                # Update pending balance with adjustment
                profile.pending_balance += adjustment_amount
                profile.save(update_fields=['pending_balance'])
        
        # Move from pending to available
        confirmed_amount = transaction.amount
        profile.pending_balance -= confirmed_amount
        profile.available_balance += confirmed_amount
        profile.lifetime_earnings += confirmed_amount
        profile.save(update_fields=['pending_balance', 'available_balance', 'lifetime_earnings'])
        
        # Update transaction status
        transaction.status = 'CONFIRMED'
        transaction.processed_at = timezone.now()
        transaction.save(update_fields=['status', 'processed_at'])
        
        return transaction


class ReconciliationService:
    """Service for handling affiliate earnings reconciliation"""
    
    @staticmethod
    def run_monthly_reconciliation(year, month):
        """Run monthly reconciliation for affiliate earnings"""
        from affiliates.models import AffiliateLink
        
        # Get date range for the month
        start_date = timezone.datetime(year, month, 1)
        if month == 12:
            end_date = timezone.datetime(year + 1, 1, 1)
        else:
            end_date = timezone.datetime(year, month + 1, 1)
        
        start_date = timezone.make_aware(start_date)
        end_date = timezone.make_aware(end_date)
        
        # Get all affiliate links that had activity in this period
        active_links = AffiliateLink.objects.filter(
            click_events__created_at__range=[start_date, end_date]
        ).distinct()
        
        total_links_processed = 0
        total_adjustment = Decimal('0.00')
        
        for link in active_links:
            # Get projected earnings for this link in the period
            projected_transactions = WalletTransaction.objects.filter(
                affiliate_link=link,
                transaction_type='EARNING_PROJECTED',
                status='PENDING',
                created_at__range=[start_date, end_date]
            )
            
            # In a real implementation, you would:
            # 1. Fetch actual revenue from affiliate program APIs
            # 2. Compare with projected amounts
            # 3. Create adjustment transactions
            # 4. Confirm projected earnings
            
            # For now, we'll just confirm all projected earnings as accurate
            for transaction in projected_transactions:
                WalletService.confirm_earning(transaction)
                total_adjustment += transaction.amount
            
            total_links_processed += 1
        
        return {
            'period': f"{year}-{month:02d}",
            'total_links_processed': total_links_processed,
            'total_adjustment': total_adjustment,
            'processed_at': timezone.now()
        }


class PayoutService:
    """Service for handling payout operations"""
    
    @staticmethod
    def validate_payout_request(user, amount, payout_method=None):
        """Validate if a payout request is valid"""
        profile = user.profile
        
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Check user eligibility
        if profile.payout_status != 'eligible':
            validation_result['is_valid'] = False
            validation_result['errors'].append("User not eligible for payouts")
        
        # Check minimum amount
        if amount < profile.min_cashout_amount:
            validation_result['is_valid'] = False
            validation_result['errors'].append(
                f"Amount ${amount} below minimum ${profile.min_cashout_amount}"
            )
        
        # Check available balance
        if amount > profile.available_balance:
            validation_result['is_valid'] = False
            validation_result['errors'].append("Insufficient available balance")
        
        # Check payout method setup
        method = payout_method or profile.preferred_payout_method
        
        if method == 'stripe_bank' and not profile.stripe_connect_account_id:
            validation_result['is_valid'] = False
            validation_result['errors'].append("Stripe Connect account not configured")
        
        if method == 'paypal' and not profile.paypal_email:
            validation_result['is_valid'] = False
            validation_result['errors'].append("PayPal email not configured")
        
        # Check for recent payout requests
        recent_requests = PayoutRequest.objects.filter(
            user=user,
            requested_at__gte=timezone.now() - timedelta(days=1)
        ).count()
        
        if recent_requests >= 3:
            validation_result['warnings'].append("Multiple payout requests in last 24 hours")
        
        return validation_result
    
    @staticmethod
    def create_payout_request(user, amount, payout_method=None, user_notes=""):
        """Create a new payout request with validation"""
        validation = PayoutService.validate_payout_request(user, amount, payout_method)
        
        if not validation['is_valid']:
            raise ValueError(f"Invalid payout request: {', '.join(validation['errors'])}")
        
        return PayoutRequest.create_from_user_request(
            user=user,
            amount=amount,
            payout_method=payout_method,
            user_notes=user_notes
        )
    
    @staticmethod
    def get_payout_summary(user):
        """Get payout summary for a user"""
        total_requested = PayoutRequest.objects.filter(user=user).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        total_completed = PayoutRequest.objects.filter(
            user=user, status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        pending_requests = PayoutRequest.objects.filter(
            user=user, status__in=['pending', 'approved', 'processing']
        ).count()
        
        return {
            'total_requested': total_requested,
            'total_completed': total_completed,
            'pending_requests': pending_requests,
            'success_rate': (total_completed / total_requested * 100) if total_requested > 0 else 0
        } 