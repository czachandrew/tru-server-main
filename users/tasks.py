from django_q.tasks import async_task, result
from django.utils import timezone
from django.db import models
from datetime import timedelta
import logging

from .models import PayoutRequest, User
from .mock_payout_service import PayoutProcessor, MockPayoutService

logger = logging.getLogger(__name__)


def process_single_payout_task(payout_id: int) -> dict:
    """
    Django Q task to process a single payout request
    
    Args:
        payout_id: ID of the payout request to process
        
    Returns:
        dict: Processing results
    """
    logger.info(f"🎯 Processing payout task for ID: {payout_id}")
    
    try:
        payout = PayoutRequest.objects.get(id=payout_id)
        
        # Process the payout
        result = PayoutProcessor.process_approved_payout(payout)
        
        logger.info(f"✅ Payout task completed for #{payout_id}: {result['status']}")
        return result
        
    except PayoutRequest.DoesNotExist:
        error_msg = f"Payout request {payout_id} not found"
        logger.error(error_msg)
        return {
            'success': False,
            'error_message': error_msg,
            'payout_id': payout_id
        }
    
    except Exception as e:
        error_msg = f"Unexpected error in payout task: {str(e)}"
        logger.error(error_msg)
        return {
            'success': False,
            'error_message': error_msg,
            'payout_id': payout_id
        }


def batch_process_payouts_task(payout_ids: list) -> dict:
    """
    Django Q task to process multiple payouts in batch
    
    Args:
        payout_ids: List of payout request IDs to process
        
    Returns:
        dict: Batch processing results
    """
    logger.info(f"🎯 Processing batch payout task for {len(payout_ids)} payouts")
    
    try:
        result = PayoutProcessor.batch_process_payouts(payout_ids)
        
        logger.info(f"✅ Batch payout task completed: {result['successful']}/{result['total_processed']} successful")
        return result
        
    except Exception as e:
        error_msg = f"Unexpected error in batch payout task: {str(e)}"
        logger.error(error_msg)
        return {
            'success': False,
            'error_message': error_msg,
            'payout_ids': payout_ids
        }


def retry_failed_payout_task(payout_id: int) -> dict:
    """
    Django Q task to retry a failed payout
    
    Args:
        payout_id: ID of the failed payout to retry
        
    Returns:
        dict: Retry results
    """
    logger.info(f"🔄 Retrying payout task for ID: {payout_id}")
    
    try:
        payout = PayoutRequest.objects.get(id=payout_id)
        
        if not payout.can_retry:
            error_msg = f"Payout {payout_id} cannot be retried"
            logger.warning(error_msg)
            return {
                'success': False,
                'error_message': error_msg,
                'payout_id': payout_id
            }
        
        result = PayoutProcessor.retry_failed_payout(payout)
        
        logger.info(f"✅ Payout retry task completed for #{payout_id}: {result['status']}")
        return result
        
    except PayoutRequest.DoesNotExist:
        error_msg = f"Payout request {payout_id} not found"
        logger.error(error_msg)
        return {
            'success': False,
            'error_message': error_msg,
            'payout_id': payout_id
        }
    
    except Exception as e:
        error_msg = f"Unexpected error in payout retry task: {str(e)}"
        logger.error(error_msg)
        return {
            'success': False,
            'error_message': error_msg,
            'payout_id': payout_id
        }


def auto_retry_failed_payouts_task() -> dict:
    """
    Scheduled Django Q task to automatically retry eligible failed payouts
    
    Returns:
        dict: Summary of auto-retry results
    """
    logger.info("🔄 Running auto-retry for failed payouts")
    
    # Find failed payouts that are eligible for retry
    eligible_payouts = PayoutRequest.objects.filter(
        status='failed',
        retry_count__lt=models.F('max_retries'),
        next_retry_at__lte=timezone.now()
    )
    
    results = {
        'total_eligible': eligible_payouts.count(),
        'processed': 0,
        'successful': 0,
        'failed': 0,
        'details': []
    }
    
    for payout in eligible_payouts:
        try:
            # Queue individual retry task
            task_id = async_task(
                'users.tasks.retry_failed_payout_task',
                payout.id,
                group='payout_retry',
                timeout=300  # 5 minutes
            )
            
            results['processed'] += 1
            results['details'].append({
                'payout_id': payout.id,
                'task_id': task_id,
                'status': 'queued'
            })
            
            logger.info(f"📤 Queued retry task {task_id} for payout #{payout.id}")
            
        except Exception as e:
            logger.error(f"Error queuing retry for payout {payout.id}: {str(e)}")
            results['failed'] += 1
            results['details'].append({
                'payout_id': payout.id,
                'error': str(e),
                'status': 'queue_failed'
            })
    
    logger.info(f"✅ Auto-retry task completed: {results['processed']} payouts queued for retry")
    return results


def cleanup_old_tasks() -> dict:
    """
    Django Q task to clean up old completed/failed tasks
    
    Returns:
        dict: Cleanup summary
    """
    logger.info("🧹 Running task cleanup")
    
    from django_q.models import Task
    
    # Clean up tasks older than 7 days
    cutoff_date = timezone.now() - timedelta(days=7)
    
    old_tasks = Task.objects.filter(
        stopped__lt=cutoff_date,
        success__in=[True, False]  # Completed or failed
    )
    
    count = old_tasks.count()
    old_tasks.delete()
    
    logger.info(f"🗑️ Cleaned up {count} old tasks")
    
    return {
        'cleaned_tasks': count,
        'cutoff_date': cutoff_date.isoformat()
    }


# Helper functions for task management
class PayoutTaskManager:
    """Manager for payout-related async tasks"""
    
    @staticmethod
    def queue_payout_processing(payout_id: int, priority: str = 'normal') -> str:
        """
        Queue a payout for background processing
        
        Args:
            payout_id: ID of payout to process
            priority: Task priority ('low', 'normal', 'high')
            
        Returns:
            str: Task ID
        """
        # Set timeout based on priority
        timeout = {
            'low': 600,      # 10 minutes
            'normal': 300,   # 5 minutes  
            'high': 180,     # 3 minutes
        }.get(priority, 300)
        
        task_id = async_task(
            'users.tasks.process_single_payout_task',
            payout_id,
            group='payout_processing',
            timeout=timeout
        )
        
        logger.info(f"📤 Queued payout processing task {task_id} for payout #{payout_id} (priority: {priority})")
        return task_id
    
    @staticmethod
    def queue_batch_processing(payout_ids: list) -> str:
        """
        Queue batch processing for multiple payouts
        
        Args:
            payout_ids: List of payout IDs to process
            
        Returns:
            str: Task ID
        """
        task_id = async_task(
            'users.tasks.batch_process_payouts_task',
            payout_ids,
            group='batch_payout_processing',
            timeout=900,  # 15 minutes for batch
            priority='high'
        )
        
        logger.info(f"📤 Queued batch processing task {task_id} for {len(payout_ids)} payouts")
        return task_id
    
    @staticmethod
    def get_task_status(task_id: str) -> dict:
        """
        Get status of a payout processing task
        
        Args:
            task_id: Task ID to check
            
        Returns:
            dict: Task status information
        """
        try:
            task_result = result(task_id)
            
            if task_result is None:
                return {'status': 'pending', 'message': 'Task is still running'}
            
            return {
                'status': 'completed',
                'result': task_result,
                'message': 'Task completed successfully'
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'message': 'Error checking task status'
            }
    
    @staticmethod
    def schedule_auto_retry() -> str:
        """
        Schedule the auto-retry task to run periodically
        
        Returns:
            str: Scheduled task ID
        """
        from django_q.tasks import schedule
        
        task_id = schedule(
            'users.tasks.auto_retry_failed_payouts_task',
            schedule_type='H',  # Hourly
            name='auto_retry_failed_payouts',
            repeats=-1  # Repeat indefinitely
        )
        
        logger.info(f"📅 Scheduled auto-retry task: {task_id}")
        return task_id
    
    @staticmethod
    def schedule_cleanup() -> str:
        """
        Schedule cleanup task to run daily
        
        Returns:
            str: Scheduled task ID
        """
        from django_q.tasks import schedule
        
        task_id = schedule(
            'users.tasks.cleanup_old_tasks',
            schedule_type='D',  # Daily
            name='cleanup_old_payout_tasks',
            repeats=-1  # Repeat indefinitely
        )
        
        logger.info(f"📅 Scheduled cleanup task: {task_id}")
        return task_id 