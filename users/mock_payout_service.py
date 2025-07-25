import random
import time
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from typing import Dict, Any, Optional
import logging

from .models import PayoutRequest, WalletTransaction

logger = logging.getLogger(__name__)


class MockPayoutService:
    """
    Mock payout service that simulates real payment processors (Stripe, PayPal)
    for testing and development purposes.
    """
    
    # Simulate realistic processing fees
    PROCESSING_FEES = {
        'stripe_bank': Decimal('0.25'),  # $0.25 per transfer
        'paypal': Decimal('0.02'),       # 2% of amount
        'check': Decimal('5.00'),        # $5 per check
        'other': Decimal('1.00'),        # $1 flat fee
    }
    
    # Simulate success rates for different methods
    SUCCESS_RATES = {
        'stripe_bank': 0.95,  # 95% success rate
        'paypal': 0.90,       # 90% success rate
        'check': 0.98,        # 98% success rate (rare failures)
        'other': 0.85,        # 85% success rate
    }
    
    # Common error scenarios
    COMMON_ERRORS = [
        "Insufficient funds in connected account",
        "Invalid bank account details", 
        "Account temporarily restricted",
        "Daily transfer limit exceeded",
        "Recipient account not found",
        "Currency conversion failed",
        "Network timeout during processing",
        "Fraud protection triggered",
    ]

    @classmethod
    def process_payout(cls, payout_request: PayoutRequest, simulate_delay: bool = True) -> Dict[str, Any]:
        """
        Simulate processing a payout request through external payment service
        
        Args:
            payout_request: The payout request to process
            simulate_delay: Whether to simulate realistic processing delays
            
        Returns:
            Dict containing processing results
        """
        logger.info(f"🔄 Mock processing payout #{payout_request.id} via {payout_request.payout_method}")
        
        # Simulate processing delay (3-10 seconds)
        if simulate_delay:
            delay = random.uniform(3, 10)
            logger.info(f"⏳ Simulating {delay:.1f}s processing delay...")
            time.sleep(delay)
        
        # Calculate processing fee
        processing_fee = cls._calculate_processing_fee(
            payout_request.amount, 
            payout_request.payout_method
        )
        net_amount = payout_request.amount - processing_fee
        
        # Simulate success/failure based on method
        success_rate = cls.SUCCESS_RATES.get(payout_request.payout_method, 0.90)
        is_successful = random.random() < success_rate
        
        if is_successful:
            return cls._simulate_successful_payout(payout_request, processing_fee, net_amount)
        else:
            return cls._simulate_failed_payout(payout_request)
    
    @classmethod
    def _calculate_processing_fee(cls, amount: Decimal, method: str) -> Decimal:
        """Calculate processing fee based on amount and method"""
        base_fee = cls.PROCESSING_FEES.get(method, Decimal('1.00'))
        
        if method == 'paypal':
            # PayPal: percentage-based fee
            return amount * base_fee
        else:
            # Others: flat fee
            return base_fee
    
    @classmethod
    def _simulate_successful_payout(cls, payout_request: PayoutRequest, processing_fee: Decimal, net_amount: Decimal) -> Dict[str, Any]:
        """Simulate a successful payout"""
        
        # Generate mock external transaction ID
        external_id = cls._generate_transaction_id(payout_request.payout_method)
        
        # Generate mock external reference
        external_ref = f"REF_{payout_request.payout_method.upper()}_{payout_request.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}"
        
        logger.info(f"✅ Mock payout successful: {external_id}")
        
        return {
            'success': True,
            'external_transaction_id': external_id,
            'external_reference': external_ref,
            'processing_fee': processing_fee,
            'net_amount': net_amount,
            'message': f'Payout processed successfully via {payout_request.get_payout_method_display()}',
            'metadata': {
                'processor': payout_request.payout_method,
                'processed_at': timezone.now().isoformat(),
                'mock_service': True,
                'processing_time': random.uniform(3, 10),
            }
        }
    
    @classmethod
    def _simulate_failed_payout(cls, payout_request: PayoutRequest) -> Dict[str, Any]:
        """Simulate a failed payout"""
        
        # Pick a random error
        error_message = random.choice(cls.COMMON_ERRORS)
        
        # Determine if this is retryable
        retryable_errors = [
            "Network timeout during processing",
            "Daily transfer limit exceeded", 
            "Currency conversion failed",
        ]
        can_retry = error_message in retryable_errors
        
        logger.warning(f"❌ Mock payout failed: {error_message}")
        
        return {
            'success': False,
            'error_message': error_message,
            'can_retry': can_retry,
            'retry_after': 3600 if can_retry else None,  # Retry after 1 hour
            'metadata': {
                'processor': payout_request.payout_method,
                'failed_at': timezone.now().isoformat(),
                'mock_service': True,
                'error_type': 'simulation',
            }
        }
    
    @classmethod
    def _generate_transaction_id(cls, method: str) -> str:
        """Generate realistic-looking transaction IDs for different processors"""
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_suffix = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
        
        if method == 'stripe_bank':
            return f"po_{timestamp}_{random_suffix}"  # Stripe payout format
        elif method == 'paypal':
            return f"PAY-{random_suffix}-{timestamp}"  # PayPal format
        elif method == 'check':
            return f"CHK{timestamp}{random_suffix[:4]}"  # Check number format
        else:
            return f"TXN_{timestamp}_{random_suffix}"
    
    @classmethod
    def simulate_webhook_notification(cls, payout_request: PayoutRequest, result: Dict[str, Any]) -> None:
        """
        Simulate webhook notifications that real payment processors send
        """
        webhook_data = {
            'event_type': 'payout.completed' if result['success'] else 'payout.failed',
            'payout_id': payout_request.id,
            'external_id': result.get('external_transaction_id'),
            'amount': str(payout_request.amount),
            'currency': 'USD',
            'status': 'completed' if result['success'] else 'failed',
            'timestamp': timezone.now().isoformat(),
            'metadata': result.get('metadata', {}),
        }
        
        logger.info(f"📡 Mock webhook notification: {webhook_data['event_type']}")
        
        # In a real implementation, this would be sent to a webhook endpoint
        # For now, we'll just log it
        return webhook_data


class PayoutProcessor:
    """
    High-level payout processor that orchestrates the entire payout workflow
    """
    
    @classmethod
    def process_approved_payout(cls, payout_request: PayoutRequest) -> Dict[str, Any]:
        """
        Process an approved payout request through the mock service
        
        Args:
            payout_request: The approved payout request
            
        Returns:
            Dict containing processing results
        """
        if payout_request.status != 'approved':
            raise ValueError(f"Payout {payout_request.id} is not in approved status")
        
        logger.info(f"🚀 Starting payout processing for #{payout_request.id}")
        
        try:
            # Mark as processing
            payout_request.mark_processing()
            
            # Process through mock service
            result = MockPayoutService.process_payout(payout_request)
            
            if result['success']:
                # Mark as completed
                payout_request.mark_completed(
                    external_transaction_id=result['external_transaction_id'],
                    net_amount=result['net_amount'],
                    processing_fee=result['processing_fee']
                )
                
                logger.info(f"✅ Payout #{payout_request.id} completed successfully")
                
                # Simulate webhook notification
                MockPayoutService.simulate_webhook_notification(payout_request, result)
                
                return {
                    'success': True,
                    'payout_id': payout_request.id,
                    'status': 'completed',
                    'message': result['message'],
                    'external_transaction_id': result['external_transaction_id'],
                    'net_amount': result['net_amount'],
                    'processing_fee': result['processing_fee'],
                }
            
            else:
                # Mark as failed
                payout_request.mark_failed(
                    error_message=result['error_message'],
                    can_retry=result['can_retry']
                )
                
                logger.error(f"❌ Payout #{payout_request.id} failed: {result['error_message']}")
                
                # Simulate webhook notification
                MockPayoutService.simulate_webhook_notification(payout_request, result)
                
                return {
                    'success': False,
                    'payout_id': payout_request.id,
                    'status': 'failed',
                    'error_message': result['error_message'],
                    'can_retry': result['can_retry'],
                    'retry_after': result.get('retry_after'),
                }
        
        except Exception as e:
            logger.error(f"💥 Unexpected error processing payout #{payout_request.id}: {str(e)}")
            
            # Mark as failed with system error
            payout_request.mark_failed(
                error_message=f"System error: {str(e)}",
                can_retry=True
            )
            
            return {
                'success': False,
                'payout_id': payout_request.id,
                'status': 'failed',
                'error_message': f"System error: {str(e)}",
                'can_retry': True,
                'retry_after': 3600,  # Retry in 1 hour
            }
    
    @classmethod
    def batch_process_payouts(cls, payout_ids: list) -> Dict[str, Any]:
        """
        Process multiple approved payouts in batch
        
        Args:
            payout_ids: List of payout request IDs to process
            
        Returns:
            Dict containing batch processing results
        """
        logger.info(f"🔄 Starting batch processing for {len(payout_ids)} payouts")
        
        results = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'details': [],
            'summary': {
                'total_amount': Decimal('0.00'),
                'successful_amount': Decimal('0.00'),
                'failed_amount': Decimal('0.00'),
                'total_fees': Decimal('0.00'),
            }
        }
        
        # Get approved payouts
        payouts = PayoutRequest.objects.filter(
            id__in=payout_ids,
            status='approved'
        )
        
        for payout in payouts:
            results['total_processed'] += 1
            results['summary']['total_amount'] += payout.amount
            
            try:
                # Process individual payout
                payout_result = cls.process_approved_payout(payout)
                
                if payout_result['success']:
                    results['successful'] += 1
                    results['summary']['successful_amount'] += payout.amount
                    results['summary']['total_fees'] += payout_result.get('processing_fee', Decimal('0.00'))
                else:
                    results['failed'] += 1
                    results['summary']['failed_amount'] += payout.amount
                
                results['details'].append(payout_result)
                
            except Exception as e:
                logger.error(f"Error processing payout {payout.id}: {str(e)}")
                results['failed'] += 1
                results['summary']['failed_amount'] += payout.amount
                results['details'].append({
                    'success': False,
                    'payout_id': payout.id,
                    'error_message': str(e),
                    'can_retry': True,
                })
        
        logger.info(f"✅ Batch processing complete: {results['successful']}/{results['total_processed']} successful")
        return results
    
    @classmethod
    def retry_failed_payout(cls, payout_request: PayoutRequest) -> Dict[str, Any]:
        """
        Retry a failed payout request
        
        Args:
            payout_request: The failed payout request to retry
            
        Returns:
            Dict containing retry results
        """
        if not payout_request.can_retry:
            raise ValueError(f"Payout {payout_request.id} cannot be retried")
        
        logger.info(f"🔄 Retrying failed payout #{payout_request.id}")
        
        # Reset status to approved for retry
        payout_request.status = 'approved'
        payout_request.save()
        
        # Process again
        return cls.process_approved_payout(payout_request)


class PayoutAnalytics:
    """Analytics service for payout processing performance"""
    
    @classmethod
    def get_processing_metrics(cls, days: int = 30) -> Dict[str, Any]:
        """Get payout processing performance metrics"""
        from django.db.models import Count, Sum, Avg
        
        cutoff_date = timezone.now() - timedelta(days=days)
        payouts = PayoutRequest.objects.filter(processed_at__gte=cutoff_date)
        
        # Calculate success rate by method
        method_stats = payouts.values('payout_method').annotate(
            total=Count('id'),
            successful=Count('id', filter=models.Q(status='completed')),
            failed=Count('id', filter=models.Q(status='failed')),
            total_amount=Sum('amount'),
            avg_processing_time=Avg('processing_time')
        )
        
        return {
            'period_days': days,
            'total_payouts': payouts.count(),
            'success_rate': payouts.filter(status='completed').count() / payouts.count() * 100 if payouts.count() > 0 else 0,
            'method_breakdown': list(method_stats),
            'total_volume': payouts.aggregate(total=Sum('amount'))['total'] or Decimal('0'),
            'avg_processing_time': payouts.aggregate(avg=Avg('processing_time'))['avg'] or 0,
        } 