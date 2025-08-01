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


class ReferralCodeService:
    """Service for managing referral codes and allocations"""
    
    @staticmethod
    def calculate_user_allocations(user):
        """Calculate equal allocations for user's active codes + user's share"""
        from users.models import UserReferralCode
        
        active_codes = UserReferralCode.objects.filter(
            user=user, 
            is_active=True
        ).select_related('referral_code', 'referral_code__promotion')
        
        if not active_codes.exists():
            return {'user': 100.0, 'codes': {}}
        
        # Filter codes that are within valid promotion timeline
        valid_codes = []
        for user_code in active_codes:
            promotion = user_code.referral_code.promotion
            if (promotion and promotion.is_active and 
                promotion.is_code_entry_open()):
                valid_codes.append(user_code)
        
        if not valid_codes:
            return {'user': 100.0, 'codes': {}}
        
        # Equal distribution among valid codes
        code_count = len(valid_codes)
        code_percentage = 100.0 / (code_count + 1)  # +1 for user's share
        
        allocations = {'user': code_percentage, 'codes': {}}
        for user_code in valid_codes:
            allocations['codes'][user_code.referral_code.id] = code_percentage
        
        return allocations
    
    @staticmethod
    def add_user_referral_code(user, referral_code, allocation_percentage=None):
        """Add a referral code to user's active codes with automatic allocation calculation"""
        from users.models import UserReferralCode, ReferralCode
        from django.core.exceptions import ValidationError
        
        # Validate the referral code exists and is active
        try:
            referral_code = ReferralCode.objects.get(
                code=referral_code,
                is_active=True
            )
        except ReferralCode.DoesNotExist:
            raise ValidationError("Invalid or inactive referral code")
        
        # Check if promotion is in code entry period
        try:
            promotion = referral_code.promotion
            if not promotion or not promotion.is_code_entry_open():
                raise ValidationError("Code entry period has ended for this promotion")
        except:
            raise ValidationError("Invalid promotion for this code")
        
        # Check if user already has this code (active or inactive)
        existing_code = UserReferralCode.objects.filter(
            user=user, 
            referral_code=referral_code
        ).first()
        
        if existing_code:
            if existing_code.is_active:
                raise ValidationError("You already have this code active")
            else:
                # Reactivate the existing code
                existing_code.is_active = True
                existing_code.added_at = timezone.now()  # Update the added date
                existing_code.save()
                user_code = existing_code
        else:
            # Calculate allocation if not provided
            if allocation_percentage is None:
                current_allocations = ReferralCodeService.calculate_user_allocations(user)
                allocation_percentage = current_allocations.get('user', 100.0)
            
            # Create new user referral code
            user_code = UserReferralCode.objects.create(
                user=user,
                referral_code=referral_code,
                allocation_percentage=allocation_percentage
            )
        
        # Recalculate all allocations to maintain equal distribution
        ReferralCodeService.recalculate_user_allocations(user)
        
        return user_code
    
    @staticmethod
    def remove_user_referral_code(user, user_referral_code_id):
        """Remove a user referral code by UserReferralCode ID and recalculate allocations"""
        from users.models import UserReferralCode
        
        try:
            user_code = UserReferralCode.objects.get(
                id=user_referral_code_id,
                user=user,  # Security check - ensure it belongs to this user
                is_active=True
            )
            user_code.is_active = False
            user_code.save()
            
            # Recalculate remaining allocations
            ReferralCodeService.recalculate_user_allocations(user)
            
            return True
        except UserReferralCode.DoesNotExist:
            return False
    
    @staticmethod
    def recalculate_user_allocations(user):
        """Recalculate allocations when codes are added/removed (affects future purchases only)"""
        from users.models import UserReferralCode
        
        active_codes = UserReferralCode.objects.filter(
            user=user, 
            is_active=True
        )
        
        if not active_codes.exists():
            return
        
        # Equal distribution among remaining codes
        code_count = active_codes.count()
        new_percentage = 100.0 / (code_count + 1)  # +1 for user's share
        
        # Update all active codes
        active_codes.update(allocation_percentage=new_percentage)
    
    @staticmethod
    def get_user_referral_summary(user):
        """Get comprehensive summary of user's referral code activity"""
        from users.models import UserReferralCode, ReferralDisbursement
        from django.db.models import Sum
        
        # Get active codes
        active_codes = UserReferralCode.objects.filter(
            user=user,
            is_active=True
        ).select_related('referral_code', 'referral_code__owner', 'referral_code__promotion')
        
        # Get total giving amount
        total_giving = ReferralDisbursement.objects.filter(
            wallet_transaction__user=user
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Get potential giving (from projected earnings)
        potential_giving = ReferralDisbursement.objects.filter(
            wallet_transaction__user=user,
            wallet_transaction__transaction_type='EARNING_PROJECTED'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Calculate current allocations
        allocations = ReferralCodeService.calculate_user_allocations(user)
        
        return {
            'active_codes': active_codes,
            'total_giving': float(total_giving),
            'potential_giving': float(potential_giving),
            'net_earnings': float(user.profile.lifetime_earnings - total_giving),
            'potential_net_earnings': float(user.profile.lifetime_earnings + user.profile.pending_balance - (total_giving + potential_giving)),
            'allocations': allocations,
            'user_allocation_percentage': float(allocations.get('user', 100.0))
        }
    
    @staticmethod
    def validate_referral_code(code):
        """Validate a referral code format and existence"""
        from users.models import ReferralCode
        
        # Check format
        if len(code) < 7:
            return False, "Code must be at least 7 characters"
        
        if sum(c.isdigit() for c in code) < 2:
            return False, "Code must contain at least 2 numbers"
        
        # Check if code exists and is active
        try:
            referral_code = ReferralCode.objects.get(code=code, is_active=True)
            
            # Check if promotion is in code entry period
            try:
                promotion = referral_code.promotion
                if not promotion or not promotion.is_code_entry_open():
                    return False, "Code entry period has ended for this promotion"
            except:
                return False, "Invalid promotion for this code"
            
            return True, referral_code
        except ReferralCode.DoesNotExist:
            return False, "Invalid or inactive referral code"


class OrganizationService:
    """Service for managing organization-related operations"""
    
    @staticmethod
    def create_organization_with_verification(user, organization_data):
        """Create an organization user with verification record"""
        from users.models import OrganizationVerification
        
        # Update user profile
        user.profile.is_organization = True
        user.profile.organization_name = organization_data.get('name', '')
        user.profile.organization_type = organization_data.get('type', '')
        user.profile.min_payout_amount = organization_data.get('min_payout_amount', 10.00)
        user.profile.save()
        
        # Create verification record
        verification = OrganizationVerification.objects.create(
            organization=user,
            verification_status='pending'
        )
        
        return user, verification
    
    @staticmethod
    def get_organization_summary(organization):
        """Get comprehensive summary of organization's referral activity"""
        from users.models import Promotion, ReferralDisbursement, UserReferralCode
        from django.db.models import Sum, Count
        
        # Get active promotions
        active_promotions = Promotion.objects.filter(
            organization=organization,
            is_active=True
        ).select_related('referral_code')
        
        # Get total received disbursements
        total_received = ReferralDisbursement.objects.filter(
            recipient_user=organization
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Get pending disbursements
        pending_disbursements = ReferralDisbursement.objects.filter(
            recipient_user=organization,
            status='pending'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Get user count for each promotion
        promotion_stats = []
        for promotion in active_promotions:
            user_count = UserReferralCode.objects.filter(
                referral_code=promotion.referral_code,
                is_active=True
            ).count()
            promotion_stats.append({
                'promotion': promotion,
                'user_count': user_count,
                'status': promotion.get_status_display()
            })
        
        return {
            'active_promotions': promotion_stats,
            'total_received': float(total_received),
            'pending_disbursements': float(pending_disbursements),
            'verification_status': organization.verification.verification_status if hasattr(organization, 'verification') else 'none'
        } 