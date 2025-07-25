"""
Withdrawal Service - Handle cash withdrawals via multiple payment methods
"""

from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
import logging
import json

from .models import User, WalletTransaction
from .services import WalletService

logger = logging.getLogger(__name__)

# Import payment processors
try:
    import stripe
    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    logger.warning("Stripe not available - install stripe package")

try:
    import paypalrestsdk
    PAYPAL_AVAILABLE = True
except ImportError:
    PAYPAL_AVAILABLE = False
    logger.warning("PayPal not available - install paypalrestsdk package")


class WithdrawalService:
    """Service for handling cash withdrawals"""
    
    WITHDRAWAL_METHODS = {
        'stripe': 'Stripe Transfer',
        'paypal': 'PayPal Payout',
        'bank_transfer': 'Bank Transfer',
        'check': 'Physical Check'
    }
    
    # Minimum withdrawal amounts by method
    MIN_WITHDRAWAL_AMOUNTS = {
        'stripe': Decimal('10.00'),
        'paypal': Decimal('10.00'),
        'bank_transfer': Decimal('25.00'),
        'check': Decimal('50.00')
    }
    
    # Processing fees by method
    PROCESSING_FEES = {
        'stripe': Decimal('0.25'),  # $0.25 per transfer
        'paypal': Decimal('0.30'),  # $0.30 per payout
        'bank_transfer': Decimal('5.00'),  # $5.00 per transfer
        'check': Decimal('2.50')  # $2.50 per check
    }

    @staticmethod
    def get_available_methods(user: User) -> Dict[str, Dict[str, Any]]:
        """Get available withdrawal methods for a user"""
        profile = user.profile
        
        methods = {}
        
        # Stripe - available if user has valid payment method
        if STRIPE_AVAILABLE:
            methods['stripe'] = {
                'name': WithdrawalService.WITHDRAWAL_METHODS['stripe'],
                'min_amount': WithdrawalService.MIN_WITHDRAWAL_AMOUNTS['stripe'],
                'fee': WithdrawalService.PROCESSING_FEES['stripe'],
                'available': profile.available_balance >= WithdrawalService.MIN_WITHDRAWAL_AMOUNTS['stripe'],
                'processing_time': '2-3 business days'
            }
        
        # PayPal - available if user has PayPal email
        if PAYPAL_AVAILABLE:
            methods['paypal'] = {
                'name': WithdrawalService.WITHDRAWAL_METHODS['paypal'],
                'min_amount': WithdrawalService.MIN_WITHDRAWAL_AMOUNTS['paypal'],
                'fee': WithdrawalService.PROCESSING_FEES['paypal'],
                'available': profile.available_balance >= WithdrawalService.MIN_WITHDRAWAL_AMOUNTS['paypal'],
                'processing_time': '1-2 business days'
            }
        
        # Bank transfer - always available
        methods['bank_transfer'] = {
            'name': WithdrawalService.WITHDRAWAL_METHODS['bank_transfer'],
            'min_amount': WithdrawalService.MIN_WITHDRAWAL_AMOUNTS['bank_transfer'],
            'fee': WithdrawalService.PROCESSING_FEES['bank_transfer'],
            'available': profile.available_balance >= WithdrawalService.MIN_WITHDRAWAL_AMOUNTS['bank_transfer'],
            'processing_time': '3-5 business days'
        }
        
        # Check - always available
        methods['check'] = {
            'name': WithdrawalService.WITHDRAWAL_METHODS['check'],
            'min_amount': WithdrawalService.MIN_WITHDRAWAL_AMOUNTS['check'],
            'fee': WithdrawalService.PROCESSING_FEES['check'],
            'available': profile.available_balance >= WithdrawalService.MIN_WITHDRAWAL_AMOUNTS['check'],
            'processing_time': '7-10 business days'
        }
        
        return methods
    
    @staticmethod
    def initiate_withdrawal(user: User, amount: Decimal, method: str, payment_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initiate a withdrawal request
        
        Args:
            user: The user requesting withdrawal
            amount: Amount to withdraw
            method: Withdrawal method (stripe, paypal, bank_transfer, check)
            payment_details: Payment method specific details
            
        Returns:
            Dict with withdrawal result
        """
        try:
            # Validate method
            if method not in WithdrawalService.WITHDRAWAL_METHODS:
                raise ValueError(f"Invalid withdrawal method: {method}")
            
            # Validate amount
            min_amount = WithdrawalService.MIN_WITHDRAWAL_AMOUNTS[method]
            if amount < min_amount:
                raise ValueError(f"Minimum withdrawal amount for {method} is ${min_amount}")
            
            # Check user balance
            profile = user.profile
            fee = WithdrawalService.PROCESSING_FEES[method]
            total_amount = amount + fee
            
            if total_amount > profile.available_balance:
                raise ValueError(f"Insufficient balance. Available: ${profile.available_balance}, Required: ${total_amount}")
            
            # Create withdrawal transaction
            withdrawal_transaction = WalletService.initiate_withdrawal(user, total_amount, method)
            
            # Process withdrawal based on method
            if method == 'stripe':
                result = WithdrawalService._process_stripe_withdrawal(
                    withdrawal_transaction, amount, fee, payment_details
                )
            elif method == 'paypal':
                result = WithdrawalService._process_paypal_withdrawal(
                    withdrawal_transaction, amount, fee, payment_details
                )
            elif method == 'bank_transfer':
                result = WithdrawalService._process_bank_transfer_withdrawal(
                    withdrawal_transaction, amount, fee, payment_details
                )
            elif method == 'check':
                result = WithdrawalService._process_check_withdrawal(
                    withdrawal_transaction, amount, fee, payment_details
                )
            
            # Update transaction with processing details
            withdrawal_transaction.metadata.update({
                'processing_result': result,
                'fee_amount': str(fee),
                'net_amount': str(amount)
            })
            withdrawal_transaction.save()
            
            # Send notification
            WithdrawalService._send_withdrawal_initiated_notification(user, amount, method)
            
            logger.info(f"Withdrawal initiated for {user.email}: ${amount} via {method}")
            
            return {
                'success': True,
                'transaction_id': withdrawal_transaction.id,
                'method': method,
                'amount': amount,
                'fee': fee,
                'total_amount': total_amount,
                'processing_result': result
            }
            
        except Exception as e:
            logger.error(f"Withdrawal initiation failed for {user.email}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def _process_stripe_withdrawal(transaction: WalletTransaction, amount: Decimal, fee: Decimal, payment_details: Dict[str, Any]) -> Dict[str, Any]:
        """Process Stripe withdrawal"""
        if not STRIPE_AVAILABLE:
            raise ValueError("Stripe not available")
        
        try:
            # Create Stripe transfer
            transfer = stripe.Transfer.create(
                amount=int(amount * 100),  # Convert to cents
                currency='usd',
                destination=payment_details.get('stripe_account_id'),
                description=f"Wallet withdrawal for {transaction.user.email}",
                metadata={
                    'transaction_id': str(transaction.id),
                    'user_email': transaction.user.email
                }
            )
            
            return {
                'status': 'processing',
                'processor_reference': transfer.id,
                'estimated_completion': ' 2-3 business days'
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe withdrawal failed: {str(e)}")
            # Fail the transaction
            WalletService.fail_withdrawal(transaction, f"Stripe error: {str(e)}")
            raise ValueError(f"Stripe processing failed: {str(e)}")
    
    @staticmethod
    def _process_paypal_withdrawal(transaction: WalletTransaction, amount: Decimal, fee: Decimal, payment_details: Dict[str, Any]) -> Dict[str, Any]:
        """Process PayPal withdrawal"""
        if not PAYPAL_AVAILABLE:
            raise ValueError("PayPal not available")
        
        try:
            # Configure PayPal
            paypalrestsdk.configure({
                'mode': getattr(settings, 'PAYPAL_MODE', 'sandbox'),
                'client_id': getattr(settings, 'PAYPAL_CLIENT_ID', ''),
                'client_secret': getattr(settings, 'PAYPAL_CLIENT_SECRET', '')
            })
            
            # Create PayPal payout
            payout = paypalrestsdk.Payout({
                'sender_batch_header': {
                    'sender_batch_id': f"wallet_withdrawal_{transaction.id}",
                    'email_subject': "Wallet Withdrawal"
                },
                'items': [{
                    'recipient_type': 'EMAIL',
                    'amount': {
                        'value': str(amount),
                        'currency': 'USD'
                    },
                    'receiver': payment_details.get('paypal_email'),
                    'note': f"Wallet withdrawal for {transaction.user.email}",
                    'sender_item_id': str(transaction.id)
                }]
            })
            
            if payout.create():
                return {
                    'status': 'processing',
                    'processor_reference': payout.batch_header.payout_batch_id,
                    'estimated_completion': '1-2 business days'
                }
            else:
                raise ValueError(f"PayPal payout creation failed: {payout.error}")
                
        except Exception as e:
            logger.error(f"PayPal withdrawal failed: {str(e)}")
            WalletService.fail_withdrawal(transaction, f"PayPal error: {str(e)}")
            raise ValueError(f"PayPal processing failed: {str(e)}")
    
    @staticmethod
    def _process_bank_transfer_withdrawal(transaction: WalletTransaction, amount: Decimal, fee: Decimal, payment_details: Dict[str, Any]) -> Dict[str, Any]:
        """Process bank transfer withdrawal"""
        # For bank transfers, we'll queue for manual processing
        # In a real implementation, this would integrate with banking APIs
        
        return {
            'status': 'pending_manual_processing',
            'processor_reference': f"BANK_{transaction.id}",
            'estimated_completion': '3-5 business days',
            'bank_details': {
                'account_number': payment_details.get('account_number', '****'),
                'routing_number': payment_details.get('routing_number', '****'),
                'bank_name': payment_details.get('bank_name', ''),
                'account_holder': payment_details.get('account_holder', '')
            }
        }
    
    @staticmethod
    def _process_check_withdrawal(transaction: WalletTransaction, amount: Decimal, fee: Decimal, payment_details: Dict[str, Any]) -> Dict[str, Any]:
        """Process check withdrawal"""
        # For checks, we'll queue for manual processing
        
        return {
            'status': 'pending_manual_processing',
            'processor_reference': f"CHECK_{transaction.id}",
            'estimated_completion': '7-10 business days',
            'mailing_address': {
                'name': payment_details.get('name', ''),
                'address1': payment_details.get('address1', ''),
                'address2': payment_details.get('address2', ''),
                'city': payment_details.get('city', ''),
                'state': payment_details.get('state', ''),
                'zip_code': payment_details.get('zip_code', ''),
                'country': payment_details.get('country', 'US')
            }
        }
    
    @staticmethod
    def handle_stripe_webhook(event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Stripe webhook events for withdrawals"""
        try:
            event_type = event_data.get('type')
            
            if event_type == 'transfer.paid':
                # Transfer completed successfully
                transfer_id = event_data['data']['object']['id']
                
                # Find the transaction
                transaction = WalletTransaction.objects.filter(
                    withdrawal_reference=transfer_id,
                    status='PROCESSING'
                ).first()
                
                if transaction:
                    WalletService.complete_withdrawal(transaction, transfer_id)
                    return {'status': 'processed'}
            
            elif event_type == 'transfer.failed':
                # Transfer failed
                transfer_id = event_data['data']['object']['id']
                failure_reason = event_data['data']['object'].get('failure_message', 'Unknown error')
                
                # Find the transaction
                transaction = WalletTransaction.objects.filter(
                    withdrawal_reference=transfer_id,
                    status='PROCESSING'
                ).first()
                
                if transaction:
                    WalletService.fail_withdrawal(transaction, f"Stripe transfer failed: {failure_reason}")
                    return {'status': 'failed'}
            
            return {'status': 'ignored'}
            
        except Exception as e:
            logger.error(f"Stripe webhook handling failed: {str(e)}")
            return {'status': 'error', 'message': str(e)}
    
    @staticmethod
    def get_withdrawal_status(transaction_id: int) -> Dict[str, Any]:
        """Get the current status of a withdrawal"""
        try:
            transaction = WalletTransaction.objects.get(id=transaction_id)
            
            if transaction.transaction_type not in ['WITHDRAWAL_PENDING', 'WITHDRAWAL_CASH', 'WITHDRAWAL_FAILED']:
                raise ValueError("Not a withdrawal transaction")
            
            return {
                'transaction_id': transaction.id,
                'status': transaction.status,
                'amount': transaction.amount,
                'method': transaction.metadata.get('withdrawal_method', 'unknown'),
                'created_at': transaction.created_at,
                'processed_at': transaction.processed_at,
                'reference': transaction.withdrawal_reference,
                'description': transaction.description
            }
            
        except WalletTransaction.DoesNotExist:
            raise ValueError("Withdrawal transaction not found")
    
    @staticmethod
    def cancel_withdrawal(transaction_id: int, reason: str = "User request") -> Dict[str, Any]:
        """Cancel a pending withdrawal"""
        try:
            transaction = WalletTransaction.objects.get(id=transaction_id)
            
            if transaction.transaction_type != 'WITHDRAWAL_PENDING':
                raise ValueError("Can only cancel pending withdrawals")
            
            if transaction.status != 'PENDING':
                raise ValueError("Withdrawal is already being processed")
            
            # Cancel the withdrawal
            WalletService.fail_withdrawal(transaction, f"Cancelled: {reason}")
            
            # Send notification
            WithdrawalService._send_withdrawal_cancelled_notification(
                transaction.user, transaction.amount, reason
            )
            
            logger.info(f"Withdrawal cancelled for {transaction.user.email}: ${transaction.amount}")
            
            return {
                'success': True,
                'transaction_id': transaction.id,
                'status': 'cancelled',
                'reason': reason
            }
            
        except WalletTransaction.DoesNotExist:
            raise ValueError("Withdrawal transaction not found")
    
    @staticmethod
    def _send_withdrawal_initiated_notification(user: User, amount: Decimal, method: str) -> None:
        """Send notification about withdrawal initiation"""
        try:
            send_mail(
                subject='Withdrawal Request Initiated',
                message=f'Your withdrawal request for ${amount} via {method} has been initiated and is being processed.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True
            )
        except Exception as e:
            logger.error(f"Failed to send withdrawal notification: {e}")
    
    @staticmethod
    def _send_withdrawal_cancelled_notification(user: User, amount: Decimal, reason: str) -> None:
        """Send notification about withdrawal cancellation"""
        try:
            send_mail(
                subject='Withdrawal Request Cancelled',
                message=f'Your withdrawal request for ${amount} has been cancelled. Reason: {reason}. The funds have been returned to your wallet.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True
            )
        except Exception as e:
            logger.error(f"Failed to send withdrawal cancellation notification: {e}")


class WithdrawalAdminService:
    """Service for admin management of withdrawals"""
    
    @staticmethod
    def get_pending_withdrawals() -> list:
        """Get all pending withdrawals for admin review"""
        pending_withdrawals = WalletTransaction.objects.filter(
            transaction_type='WITHDRAWAL_PENDING',
            status='PENDING'
        ).select_related('user').order_by('-created_at')
        
        return [
            {
                'id': w.id,
                'user': w.user.email,
                'amount': w.amount,
                'method': w.metadata.get('withdrawal_method', 'unknown'),
                'created_at': w.created_at,
                'fee': w.metadata.get('fee_amount', '0.00'),
                'net_amount': w.metadata.get('net_amount', str(w.amount))
            }
            for w in pending_withdrawals
        ]
    
    @staticmethod
    def approve_withdrawal(transaction_id: int, admin_user: User) -> Dict[str, Any]:
        """Approve a pending withdrawal (for manual processing methods)"""
        try:
            transaction = WalletTransaction.objects.get(id=transaction_id)
            
            if transaction.transaction_type != 'WITHDRAWAL_PENDING':
                raise ValueError("Not a pending withdrawal")
            
            # Mark as approved and set admin
            transaction.processed_by = admin_user
            transaction.status = 'PROCESSING'
            transaction.save()
            
            # Generate reference
            reference = f"ADMIN_APPROVED_{transaction.id}"
            
            # Complete the withdrawal
            WalletService.complete_withdrawal(transaction, reference)
            
            logger.info(f"Withdrawal approved by admin {admin_user.email}: Transaction {transaction.id}")
            
            return {
                'success': True,
                'transaction_id': transaction.id,
                'reference': reference,
                'approved_by': admin_user.email
            }
            
        except WalletTransaction.DoesNotExist:
            raise ValueError("Withdrawal transaction not found")
    
    @staticmethod
    def reject_withdrawal(transaction_id: int, admin_user: User, reason: str) -> Dict[str, Any]:
        """Reject a pending withdrawal"""
        try:
            transaction = WalletTransaction.objects.get(id=transaction_id)
            
            if transaction.transaction_type != 'WITHDRAWAL_PENDING':
                raise ValueError("Not a pending withdrawal")
            
            # Mark as rejected
            transaction.processed_by = admin_user
            transaction.save()
            
            # Fail the withdrawal
            WalletService.fail_withdrawal(transaction, f"Rejected by admin: {reason}")
            
            logger.info(f"Withdrawal rejected by admin {admin_user.email}: Transaction {transaction.id}")
            
            return {
                'success': True,
                'transaction_id': transaction.id,
                'rejected_by': admin_user.email,
                'reason': reason
            }
            
        except WalletTransaction.DoesNotExist:
            raise ValueError("Withdrawal transaction not found") 