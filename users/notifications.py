"""
Notification Service for Wallet Events
"""

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional
import logging

from .models import User, WalletTransaction

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending wallet-related notifications"""
    
    NOTIFICATION_TYPES = {
        'EARNING_CONFIRMED': 'Earnings Added',
        'WITHDRAWAL_INITIATED': 'Withdrawal Started',
        'WITHDRAWAL_COMPLETED': 'Withdrawal Completed',
        'WITHDRAWAL_FAILED': 'Withdrawal Failed',
        'WITHDRAWAL_CANCELLED': 'Withdrawal Cancelled',
        'ACTIVITY_BONUS': 'Activity Bonus',
        'BALANCE_THRESHOLD': 'Balance Threshold',
        'MONTHLY_SUMMARY': 'Monthly Summary',
        'RECONCILIATION_COMPLETE': 'Reconciliation Complete',
    }
    
    @staticmethod
    def send_earning_notification(user: User, amount: Decimal, transaction: WalletTransaction) -> bool:
        """Send notification when user receives confirmed earnings"""
        try:
            context = {
                'user': user,
                'amount': amount,
                'transaction': transaction,
                'balance': user.profile.available_balance,
                'activity_score': user.profile.activity_score,
                'revenue_share_rate': user.profile.revenue_share_rate,
                'platform': transaction.affiliate_link.platform if transaction.affiliate_link else 'Unknown'
            }
            
            subject = f"${amount} Added to Your Wallet!"
            
            # Send email
            success = NotificationService._send_email_notification(
                user=user,
                subject=subject,
                template_name='wallet/notifications/earning_confirmed.html',
                context=context
            )
            
            # Log notification
            if success:
                logger.info(f"Earning notification sent to {user.email}: ${amount}")
            else:
                logger.error(f"Failed to send earning notification to {user.email}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending earning notification: {str(e)}")
            return False
    
    @staticmethod
    def send_withdrawal_initiated_notification(user: User, amount: Decimal, method: str, estimated_completion: str) -> bool:
        """Send notification when withdrawal is initiated"""
        try:
            context = {
                'user': user,
                'amount': amount,
                'method': method,
                'estimated_completion': estimated_completion,
                'remaining_balance': user.profile.available_balance
            }
            
            subject = f"Withdrawal Request for ${amount} Started"
            
            success = NotificationService._send_email_notification(
                user=user,
                subject=subject,
                template_name='wallet/notifications/withdrawal_initiated.html',
                context=context
            )
            
            if success:
                logger.info(f"Withdrawal initiated notification sent to {user.email}: ${amount}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending withdrawal initiated notification: {str(e)}")
            return False
    
    @staticmethod
    def send_withdrawal_completed_notification(user: User, amount: Decimal, method: str, reference: str) -> bool:
        """Send notification when withdrawal is completed"""
        try:
            context = {
                'user': user,
                'amount': amount,
                'method': method,
                'reference': reference,
                'completion_date': timezone.now(),
                'remaining_balance': user.profile.available_balance
            }
            
            subject = f"Withdrawal of ${amount} Completed"
            
            success = NotificationService._send_email_notification(
                user=user,
                subject=subject,
                template_name='wallet/notifications/withdrawal_completed.html',
                context=context
            )
            
            if success:
                logger.info(f"Withdrawal completed notification sent to {user.email}: ${amount}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending withdrawal completed notification: {str(e)}")
            return False
    
    @staticmethod
    def send_withdrawal_failed_notification(user: User, amount: Decimal, method: str, reason: str) -> bool:
        """Send notification when withdrawal fails"""
        try:
            context = {
                'user': user,
                'amount': amount,
                'method': method,
                'reason': reason,
                'restored_balance': user.profile.available_balance
            }
            
            subject = f"Withdrawal of ${amount} Failed"
            
            success = NotificationService._send_email_notification(
                user=user,
                subject=subject,
                template_name='wallet/notifications/withdrawal_failed.html',
                context=context
            )
            
            if success:
                logger.info(f"Withdrawal failed notification sent to {user.email}: ${amount}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending withdrawal failed notification: {str(e)}")
            return False
    
    @staticmethod
    def send_activity_bonus_notification(user: User, amount: Decimal, old_score: Decimal, new_score: Decimal) -> bool:
        """Send notification when user receives activity bonus"""
        try:
            context = {
                'user': user,
                'amount': amount,
                'old_score': old_score,
                'new_score': new_score,
                'new_revenue_share_rate': user.profile.revenue_share_rate,
                'balance': user.profile.available_balance
            }
            
            subject = f"Activity Bonus: ${amount} Added!"
            
            success = NotificationService._send_email_notification(
                user=user,
                subject=subject,
                template_name='wallet/notifications/activity_bonus.html',
                context=context
            )
            
            if success:
                logger.info(f"Activity bonus notification sent to {user.email}: ${amount}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending activity bonus notification: {str(e)}")
            return False
    
    @staticmethod
    def send_balance_threshold_notification(user: User, threshold_type: str, threshold_amount: Decimal) -> bool:
        """Send notification when balance reaches certain thresholds"""
        try:
            context = {
                'user': user,
                'threshold_type': threshold_type,
                'threshold_amount': threshold_amount,
                'current_balance': user.profile.available_balance,
                'min_cashout_amount': user.profile.min_cashout_amount
            }
            
            if threshold_type == 'cashout_available':
                subject = f"Ready to Cash Out - ${user.profile.available_balance} Available"
            elif threshold_type == 'milestone_reached':
                subject = f"Milestone Reached - ${user.profile.available_balance} in Your Wallet"
            else:
                subject = f"Wallet Balance Update - ${user.profile.available_balance}"
            
            success = NotificationService._send_email_notification(
                user=user,
                subject=subject,
                template_name='wallet/notifications/balance_threshold.html',
                context=context
            )
            
            if success:
                logger.info(f"Balance threshold notification sent to {user.email}: {threshold_type}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending balance threshold notification: {str(e)}")
            return False
    
    @staticmethod
    def send_monthly_summary_notification(user: User, summary_data: Dict[str, Any]) -> bool:
        """Send monthly wallet summary notification"""
        try:
            context = {
                'user': user,
                'summary_data': summary_data,
                'current_balance': user.profile.available_balance,
                'activity_score': user.profile.activity_score,
                'revenue_share_rate': user.profile.revenue_share_rate
            }
            
            subject = f"Monthly Wallet Summary - {summary_data.get('period', 'This Month')}"
            
            success = NotificationService._send_email_notification(
                user=user,
                subject=subject,
                template_name='wallet/notifications/monthly_summary.html',
                context=context
            )
            
            if success:
                logger.info(f"Monthly summary notification sent to {user.email}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending monthly summary notification: {str(e)}")
            return False
    
    @staticmethod
    def _send_email_notification(user: User, subject: str, template_name: str, context: Dict[str, Any]) -> bool:
        """Send email notification with template"""
        try:
            # Add common context variables
            context.update({
                'site_name': getattr(settings, 'SITE_NAME', 'Ecommerce Platform'),
                'site_url': getattr(settings, 'BASE_URL', 'http://localhost:8000'),
                'support_email': getattr(settings, 'SUPPORT_EMAIL', settings.DEFAULT_FROM_EMAIL),
                'current_year': timezone.now().year
            })
            
            # Render email content
            try:
                html_content = render_to_string(template_name, context)
                
                # Create plain text version (simplified)
                plain_text = NotificationService._html_to_plain_text(html_content)
                
            except Exception as template_error:
                logger.error(f"Template rendering failed: {str(template_error)}")
                # Fallback to simple text message
                plain_text = NotificationService._create_fallback_message(subject, context)
                html_content = None
            
            # Send email
            if html_content:
                send_mail(
                    subject=subject,
                    message=plain_text,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    html_message=html_content,
                    fail_silently=False
                )
            else:
                send_mail(
                    subject=subject,
                    message=plain_text,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email notification to {user.email}: {str(e)}")
            return False
    
    @staticmethod
    def _html_to_plain_text(html_content: str) -> str:
        """Convert HTML content to plain text"""
        # Simple HTML to text conversion
        # In production, you might want to use a library like html2text
        import re
        
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', html_content)
        
        # Clean up whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        
        return clean
    
    @staticmethod
    def _create_fallback_message(subject: str, context: Dict[str, Any]) -> str:
        """Create a fallback plain text message when templates fail"""
        user = context.get('user')
        amount = context.get('amount')
        
        message = f"Hello {user.get_full_name() or user.email},\n\n"
        message += f"Subject: {subject}\n\n"
        
        if amount:
            message += f"Amount: ${amount}\n"
        
        message += f"Current Balance: ${user.profile.available_balance}\n\n"
        message += "Thank you for using our platform!\n\n"
        message += f"Best regards,\nThe {context.get('site_name', 'Ecommerce Platform')} Team"
        
        return message
    
    @staticmethod
    def check_balance_thresholds(user: User) -> List[str]:
        """Check if user's balance has reached any notification thresholds"""
        notifications_sent = []
        balance = user.profile.available_balance
        
        try:
            # Check if user can now cash out
            if balance >= user.profile.min_cashout_amount:
                # Check if we've already sent this notification recently
                recent_threshold_notification = WalletTransaction.objects.filter(
                    user=user,
                    transaction_type='BONUS_ACTIVITY',
                    description__icontains='cashout_available',
                    created_at__gte=timezone.now() - timezone.timedelta(days=7)
                ).exists()
                
                if not recent_threshold_notification:
                    if NotificationService.send_balance_threshold_notification(
                        user, 'cashout_available', user.profile.min_cashout_amount
                    ):
                        notifications_sent.append('cashout_available')
            
            # Check milestone thresholds
            milestones = [Decimal('50.00'), Decimal('100.00'), Decimal('250.00'), Decimal('500.00')]
            
            for milestone in milestones:
                if balance >= milestone:
                    # Check if we've already sent this milestone notification
                    milestone_notification = WalletTransaction.objects.filter(
                        user=user,
                        transaction_type='BONUS_ACTIVITY',
                        description__icontains=f'milestone_{milestone}',
                        created_at__gte=timezone.now() - timezone.timedelta(days=30)
                    ).exists()
                    
                    if not milestone_notification:
                        if NotificationService.send_balance_threshold_notification(
                            user, 'milestone_reached', milestone
                        ):
                            notifications_sent.append(f'milestone_{milestone}')
                            
                            # Create a small record to track this milestone
                            WalletTransaction.objects.create(
                                user=user,
                                transaction_type='BONUS_ACTIVITY',
                                amount=Decimal('0.00'),
                                balance_before=balance,
                                balance_after=balance,
                                description=f'Milestone notification sent: ${milestone}',
                                status='CONFIRMED',
                                processed_at=timezone.now(),
                                metadata={'milestone': str(milestone), 'notification_type': 'milestone_reached'}
                            )
                        break  # Only send one milestone notification at a time
            
            return notifications_sent
            
        except Exception as e:
            logger.error(f"Error checking balance thresholds for {user.email}: {str(e)}")
            return []


class NotificationBatchService:
    """Service for sending batch notifications"""
    
    @staticmethod
    def send_monthly_summaries(year: int, month: int) -> Dict[str, Any]:
        """Send monthly wallet summaries to all active users"""
        from datetime import datetime
        import calendar
        
        # Get all users with wallet activity
        users_with_activity = User.objects.filter(
            wallet_transactions__created_at__year=year,
            wallet_transactions__created_at__month=month
        ).distinct()
        
        results = {
            'total_users': users_with_activity.count(),
            'notifications_sent': 0,
            'notifications_failed': 0,
            'errors': []
        }
        
        period_start = datetime(year, month, 1)
        period_end = datetime(year, month, calendar.monthrange(year, month)[1])
        
        for user in users_with_activity:
            try:
                # Calculate monthly summary
                monthly_transactions = WalletTransaction.objects.filter(
                    user=user,
                    created_at__gte=period_start,
                    created_at__lte=period_end
                )
                
                earnings = monthly_transactions.filter(
                    transaction_type='EARNING_CONFIRMED'
                ).aggregate(total=sum('amount'))['total'] or Decimal('0.00')
                
                withdrawals = monthly_transactions.filter(
                    transaction_type='WITHDRAWAL_CASH'
                ).aggregate(total=sum('amount'))['total'] or Decimal('0.00')
                
                spending = monthly_transactions.filter(
                    transaction_type='SPENDING_STORE'
                ).aggregate(total=sum('amount'))['total'] or Decimal('0.00')
                
                summary_data = {
                    'period': f'{year}-{month:02d}',
                    'earnings': earnings,
                    'withdrawals': withdrawals,
                    'spending': spending,
                    'net_change': earnings - withdrawals - spending,
                    'transaction_count': monthly_transactions.count()
                }
                
                # Send notification
                if NotificationService.send_monthly_summary_notification(user, summary_data):
                    results['notifications_sent'] += 1
                else:
                    results['notifications_failed'] += 1
                    
            except Exception as e:
                results['notifications_failed'] += 1
                results['errors'].append(f"{user.email}: {str(e)}")
                logger.error(f"Failed to send monthly summary to {user.email}: {str(e)}")
        
        logger.info(f"Monthly summaries sent: {results['notifications_sent']}/{results['total_users']}")
        return results
    
    @staticmethod
    def send_reconciliation_notifications(reconciliation_results: Dict[str, Any]) -> bool:
        """Send notifications to admins about reconciliation results"""
        try:
            # Get admin users
            admin_users = User.objects.filter(is_staff=True, is_active=True)
            
            context = {
                'reconciliation_results': reconciliation_results,
                'period': reconciliation_results.get('period'),
                'total_adjustment': reconciliation_results.get('total_adjustment'),
                'accuracy_percentage': reconciliation_results.get('accuracy_percentage')
            }
            
            subject = f"Monthly Reconciliation Complete - {reconciliation_results.get('period')}"
            
            for admin in admin_users:
                context['user'] = admin
                
                NotificationService._send_email_notification(
                    user=admin,
                    subject=subject,
                    template_name='wallet/notifications/reconciliation_complete.html',
                    context=context
                )
            
            logger.info(f"Reconciliation notifications sent to {admin_users.count()} admins")
            return True
            
        except Exception as e:
            logger.error(f"Error sending reconciliation notifications: {str(e)}")
            return False


# Utility functions for integration with existing services
def notify_earning_confirmed(user: User, amount: Decimal, transaction: WalletTransaction) -> None:
    """Convenience function to send earning notification and check thresholds"""
    NotificationService.send_earning_notification(user, amount, transaction)
    NotificationService.check_balance_thresholds(user)


def notify_withdrawal_status_change(user: User, transaction: WalletTransaction, status: str, **kwargs) -> None:
    """Convenience function to send withdrawal status notifications"""
    if status == 'initiated':
        NotificationService.send_withdrawal_initiated_notification(
            user, transaction.amount, kwargs.get('method', 'unknown'), kwargs.get('estimated_completion', 'unknown')
        )
    elif status == 'completed':
        NotificationService.send_withdrawal_completed_notification(
            user, transaction.amount, kwargs.get('method', 'unknown'), kwargs.get('reference', 'unknown')
        )
    elif status == 'failed':
        NotificationService.send_withdrawal_failed_notification(
            user, transaction.amount, kwargs.get('method', 'unknown'), kwargs.get('reason', 'unknown')
        )


def notify_activity_bonus(user: User, amount: Decimal, old_score: Decimal, new_score: Decimal) -> None:
    """Convenience function to send activity bonus notification"""
    NotificationService.send_activity_bonus_notification(user, amount, old_score, new_score)
    NotificationService.check_balance_thresholds(user) 