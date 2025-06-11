import os
import uuid
import json
import redis
import logging
from django.conf import settings
from affiliates.models import AffiliateLink
from django_q.tasks import async_task
from django_q.models import Schedule
from django.utils import timezone
import datetime
from django.db import models
from django.core.management.base import BaseCommand

from django_q.brokers import get_broker
from django_q.conf import Conf
from urllib.parse import urlparse

# Set up dedicated logger
logger = logging.getLogger('affiliate_tasks')

def get_redis_connection():
    if 'REDISCLOUD_URL' in os.environ:
        url = urlparse(os.environ['REDISCLOUD_URL'])
        return {
            'host': url.hostname,
            'port': url.port,
            'password': url.password,
            'decode_responses': True
        }
    else:
        redis_kwargs = {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', 6379)),
            'decode_responses': True
        }
        if os.getenv('REDIS_PASSWORD'):
            redis_kwargs['password'] = os.getenv('REDIS_PASSWORD')
        return redis_kwargs

def generate_amazon_affiliate_url(affiliate_link_id, asin):
    """Generate an Amazon affiliate URL via puppeteer worker with callback URL"""
    logger.info(f"Starting generate_amazon_affiliate_url: affiliate_link_id={affiliate_link_id}, asin={asin}")
    try:
        # Get Redis connection
        redis_kwargs = get_redis_connection()
        r = redis.Redis(**redis_kwargs)
        
        # Generate a unique task ID
        task_id = str(uuid.uuid4())
        logger.info(f"Generated task_id: {task_id}")
        
        # Store the affiliate_link_id in Redis with task_id as key
        r.set(f"pending_affiliate_task:{task_id}", affiliate_link_id, ex=86400)  # 24hr expiry
        
        # Determine base URL for callback - use settings or fallback
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        callback_url = f"{base_url}/api/affiliate/callback/{task_id}/"
        
        # Create task message with callback URL
        task_data = {
            "asin": asin,
            "taskId": task_id,
            "callbackUrl": callback_url
        }
        
        # Publish to the channel that puppeteer worker is listening on
        publish_result = r.publish("affiliate_tasks", json.dumps(task_data))
        logger.info(f"Published to Redis channel 'affiliate_tasks': {publish_result} clients received")
        
        # Schedule a safety check
        schedule_time = timezone.now() + datetime.timedelta(hours=1)
        
        Schedule.objects.create(
            name=f"safety_check_affiliate_{task_id}",
            func='affiliates.tasks.check_stalled_affiliate_task',
            args=json.dumps([task_id]),
            schedule_type=Schedule.ONCE,
            next_run=schedule_time
        )
        
        return True
    except Exception as e:
        logger.error(f"Error generating Amazon affiliate URL: {str(e)}", exc_info=True)
        return False

def task_success_handler(task):
    """
    Success handler for completed tasks
    """
    logger.info(f"Task completed: {task.id} - {task.func}")
    return True

def check_affiliate_link_status(affiliate_link_id, task_id, retry_count=0):
    """
    Check if the puppeteer worker has completed the affiliate link generation.
    If not, schedule another check with exponential backoff.
    """
    logger.info(f"Checking status for affiliate_link_id={affiliate_link_id}, task_id={task_id}, retry={retry_count}")
    try:
        # Get Redis settings with fallbacks
        redis_host = getattr(settings, 'REDIS_HOST', os.environ.get('REDIS_HOST', 'localhost'))
        redis_port = int(getattr(settings, 'REDIS_PORT', os.environ.get('REDIS_PORT', 6379)))
        redis_db = int(getattr(settings, 'REDIS_DB', os.environ.get('REDIS_DB', 0)))
        
        # Connect to Redis
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        
        # Check if the result is available
        logger.debug(f"Checking Redis key: affiliate_link:{task_id}")
        result = r.get(f"affiliate_link:{task_id}")
        logger.info(f"Redis result for task {task_id}: {result}")
        
        if result:
            if result.startswith("ERROR:"):
                logger.error(f"Puppeteer worker reported error: {result}")
                # Handle the error - could retry or notify admins
                return False
            
            # Update the affiliate link with the generated URL
            affiliate_link = AffiliateLink.objects.get(pk=affiliate_link_id)
            old_url = affiliate_link.affiliate_url
            affiliate_link.affiliate_url = result
            affiliate_link.save()
            
            logger.info(f"Updated affiliate_link_id={affiliate_link_id} with URL: '{old_url}' -> '{result}'")
            
            # Clean up the Redis key
            r.delete(f"affiliate_link:{task_id}")
            logger.debug(f"Deleted Redis key: affiliate_link:{task_id}")
            
            return True
        else:
            # Result not available yet, schedule another check with backoff
            if retry_count < 12:  # Limit retries to avoid infinite loops
                # Exponential backoff: 10s, 20s, 40s, etc. up to ~11 hours total
                next_check = 10 * (2 ** retry_count)
                schedule_time = timezone.now() + datetime.timedelta(seconds=next_check)
                
                # FIX: Use json.dumps for the args
                Schedule.objects.create(
                    name=f"check_affiliate_{task_id}_retry_{retry_count+1}",
                    func='affiliates.tasks.check_affiliate_link_status',
                    args=json.dumps([affiliate_link_id, task_id, retry_count+1]),  # Fix here
                    schedule_type=Schedule.ONCE,
                    next_run=schedule_time
                )
                
                logger.info(f"Result not available, scheduled retry #{retry_count+1} at {schedule_time}")
            else:
                logger.warning(f"Giving up on task {task_id} after {retry_count} retries")
                # Mark the affiliate link as failed in some way
                try:
                    affiliate_link = AffiliateLink.objects.get(pk=affiliate_link_id)
                    affiliate_link.affiliate_url = "ERROR: Generation timed out"
                    affiliate_link.save()
                    logger.info(f"Marked affiliate_link_id={affiliate_link_id} as failed")
                except Exception as e:
                    logger.error(f"Error marking affiliate link as failed: {str(e)}")
                
            return False
    except Exception as e:
        logger.error(f"Error checking affiliate link status: {str(e)}", exc_info=True)
        return False

def debug_affiliate_links():
    """
    Helper function to check all affiliate links in the database
    Can be called from Django shell or scheduled regularly
    """
    all_links = AffiliateLink.objects.all()
    
    logger.info(f"=== AFFILIATE LINKS REPORT ({all_links.count()} total) ===")
    
    for link in all_links:
        status = "COMPLETE" if link.affiliate_url else "PENDING"
        logger.info(f"Link ID: {link.id} | Product: {link.product.name} | ASIN: {link.platform_id} | Status: {status}")
        
    # Check for any pending tasks in Redis
    try:
        redis_host = getattr(settings, 'REDIS_HOST', os.environ.get('REDIS_HOST', 'localhost'))
        redis_port = int(getattr(settings, 'REDIS_PORT', os.environ.get('REDIS_PORT', 6379)))
        redis_db = int(getattr(settings, 'REDIS_DB', os.environ.get('REDIS_DB', 0)))
        
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        
        # Use pattern matching to find all affiliate link keys
        keys = r.keys("affiliate_link:*")
        logger.info(f"Found {len(keys)} pending tasks in Redis")
        
        for key in keys:
            value = r.get(key)
            logger.info(f"  {key}: {value}")
            
    except Exception as e:
        logger.error(f"Error checking Redis for pending tasks: {str(e)}")
    
    logger.info("=== END REPORT ===")
    return True

def check_stalled_affiliate_task(task_id):
    """Safety check for stalled affiliate tasks"""
    logger.info(f"Safety check for task_id: {task_id}")
    
    try:
        # Redis connection with proper fallbacks
        redis_kwargs = {
            'host': getattr(settings, 'REDIS_HOST', 'localhost'),
            'port': getattr(settings, 'REDIS_PORT', 6379),
            'decode_responses': True
        }
        
        # Only add password if it exists in settings
        if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
            redis_kwargs['password'] = settings.REDIS_PASSWORD
            
        r = redis.Redis(**redis_kwargs)
        
        # Check if the task is still pending
        affiliate_link_id = r.get(f"pending_affiliate_task:{task_id}")
        if not affiliate_link_id:
            logger.info(f"No pending task found for task_id: {task_id}, assuming completed")
            return
        
        # The task is stalled, mark it as failed
        affiliate_link = AffiliateLink.objects.get(pk=affiliate_link_id)
        affiliate_link.affiliate_url = "ERROR: Generation timed out"
        affiliate_link.save()
        
        # Add error data for clients polling the status
        result_data = {
            "affiliate_link_id": affiliate_link.id,
            "status": "error",
            "affiliate_url": None,
            "error": "Generation timed out after 1 hour",
            "timestamp": timezone.now().isoformat()
        }
        r.set(f"affiliate_task_status:{task_id}", json.dumps(result_data), ex=3600)
        
        # Clean up Redis
        r.delete(f"pending_affiliate_task:{task_id}")
        
        logger.warning(f"Marked stalled task {task_id} as failed after timeout")
    except Exception as e:
        logger.error(f"Error checking stalled task: {str(e)}", exc_info=True)

def get_redis_kwargs():
    """Helper function to get Redis connection parameters"""
    redis_kwargs = {
        'host': getattr(settings, 'REDIS_HOST', 'localhost'),
        'port': getattr(settings, 'REDIS_PORT', 6379),
        'decode_responses': True
    }
    if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
        redis_kwargs['password'] = settings.REDIS_PASSWORD
    return redis_kwargs

def generate_standalone_amazon_affiliate_url(asin):
    """
    Generate an Amazon affiliate URL without an existing product
    
    SAFETY CHECKS ADDED:
    - Check if affiliate link already exists with complete URL
    - Check if processing is already in progress
    - Update processing state properly
    """
    logger.info(f"🔍 SAFETY CHECK: Starting affiliate URL generation for ASIN: {asin}")
    
    try:
        # STEP 1: Check if affiliate link already exists and is complete
        existing_link = AffiliateLink.objects.filter(
            platform='amazon',
            platform_id=asin
        ).first()
        
        if existing_link:
            # Check if link is already complete
            if existing_link.affiliate_url and existing_link.affiliate_url.strip() and not existing_link.affiliate_url.startswith('ERROR:'):
                logger.info(f"✅ DUPLICATE PREVENTED: ASIN {asin} already has complete affiliate URL")
                return None, False  # Don't create duplicate task
            
            # Check if processing is already in progress
            if hasattr(existing_link, 'is_processing') and existing_link.is_processing:
                from django.utils import timezone
                from datetime import timedelta
                
                if existing_link.processing_started_at:
                    time_since_start = timezone.now() - existing_link.processing_started_at
                    if time_since_start < timedelta(minutes=10):  # Still processing
                        logger.info(f"⏳ DUPLICATE PREVENTED: ASIN {asin} already processing for {time_since_start}")
                        return None, False  # Don't create duplicate task
                    else:
                        logger.warning(f"⏰ RESETTING: Processing stuck for {time_since_start}, proceeding with new task")
                        existing_link.is_processing = False
                        existing_link.processing_started_at = None
                        existing_link.save(update_fields=['is_processing', 'processing_started_at'])
                else:
                    logger.warning(f"🔧 FIXING: is_processing=True but no start time, resetting...")
                    existing_link.is_processing = False
                    existing_link.save(update_fields=['is_processing'])
        
        # STEP 2: Generate task and update processing state
        task_id = str(uuid.uuid4())
        logger.info(f"🚀 PROCEEDING: Generating affiliate URL for ASIN: {asin} with task_id: {task_id}")
        
        redis_kwargs = get_redis_connection()
        r = redis.Redis(**redis_kwargs)
        r.set(f"pending_standalone_task:{task_id}", asin, ex=86400)
        
        # STEP 3: Update processing state if link exists
        if existing_link:
            from django.utils import timezone
            existing_link.is_processing = True
            existing_link.processing_started_at = timezone.now()
            existing_link.save(update_fields=['is_processing', 'processing_started_at'])
            logger.info(f"🔄 UPDATED: Set processing state for existing link {existing_link.id}")
        
        # STEP 4: Create and publish task
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        callback_url = f"{base_url}/api/affiliate/standalone/{task_id}/"
        
        task_data = {
            "asin": asin,
            "taskId": task_id,
            "callbackUrl": callback_url,
            "type": "amazon_standalone"
        }
        
        publish_result = r.publish("affiliate_tasks", json.dumps(task_data))
        logger.info(f"✅ PUBLISHED: Task to Redis channel 'affiliate_tasks': {publish_result} clients received")
        
        return task_id, True
        
    except redis.exceptions.AuthenticationError as e:
        logger.error(f"❌ Redis authentication error: {str(e)}")
        return None, False
    except Exception as e:
        logger.error(f"❌ Unexpected error in affiliate URL generation: {str(e)}", exc_info=True)
        return None, False

def check_stalled_standalone_task(task_id, asin):
    """Safety check for stalled standalone affiliate tasks"""
    logger.info(f"Safety check for standalone task_id: {task_id}")
    
    try:
        # Redis connection with proper fallbacks
        redis_kwargs = {
            'host': getattr(settings, 'REDIS_HOST', 'localhost'),
            'port': getattr(settings, 'REDIS_PORT', 6379),
            'decode_responses': True
        }
        
        # Only add password if it exists in settings
        if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
            redis_kwargs['password'] = settings.REDIS_PASSWORD
            
        r = redis.Redis(**redis_kwargs)
        
        # Check if the task is still pending
        stored_asin = r.get(f"pending_standalone_task:{task_id}")
        if not stored_asin:
            logger.info(f"No pending standalone task found for task_id: {task_id}, assuming completed")
            return
        
        # The task is stalled, mark it as failed
        # Add error data for clients polling the status
        result_data = {
            "status": "error",
            "affiliate_url": None,
            "error": "Generation timed out after 1 hour",
            "timestamp": timezone.now().isoformat()
        }
        r.set(f"standalone_task_status:{task_id}", json.dumps(result_data), ex=3600)
        
        # Clean up Redis
        r.delete(f"pending_standalone_task:{task_id}")
        
        logger.warning(f"Marked stalled standalone task {task_id} for ASIN {asin} as failed after timeout")
    except Exception as e:
        logger.error(f"Error checking stalled standalone task: {str(e)}", exc_info=True)

def generate_affiliate_url_from_search(search_term, search_type='part_number'):
    """
    Generate affiliate URL by searching Amazon first, then creating affiliate link
    
    This sends a search task to the Puppeteer worker which will:
    1. Search Amazon for the search term
    2. Select the best matching product
    3. Generate an affiliate link for that product
    4. Return both the affiliate URL and product data
    
    Args:
        search_term (str): The term to search for (part number, product name, etc.)
        search_type (str): Type of search - 'part_number', 'product_name', or 'general'
    
    Returns:
        tuple: (task_id, success_boolean)
    """
    logger.info(f"🔍 Creating Amazon search task: '{search_term}' (type: {search_type})")
    
    try:
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        
        # Get Redis connection
        redis_kwargs = get_redis_connection()
        r = redis.Redis(**redis_kwargs)
        
        # Create search task message for Puppeteer worker
        message = {
            'taskType': 'amazon_search',
            'searchTerm': search_term,
            'searchType': search_type,
            'taskId': task_id,
            'callbackUrl': f"{getattr(settings, 'BASE_URL', 'http://localhost:8000')}/api/affiliate-search-callback/"
        }
        
        # Store pending task info for tracking (expires in 1 hour)
        r.set(f"pending_search_task:{task_id}", json.dumps({
            'searchTerm': search_term,
            'searchType': search_type,
            'timestamp': timezone.now().isoformat()
        }), ex=3600)
        
        # Publish to the affiliate_tasks channel that Puppeteer worker is listening to
        publish_result = r.publish('affiliate_tasks', json.dumps(message))
        logger.info(f"✅ Amazon search task queued: task_id={task_id}, clients_notified={publish_result}")
        
        # Schedule a safety check in case the task stalls
        schedule_time = timezone.now() + datetime.timedelta(hours=1)
        Schedule.objects.create(
            name=f"safety_check_search_{task_id}",
            func='affiliates.tasks.check_stalled_search_task',
            args=json.dumps([task_id, search_term]),
            schedule_type=Schedule.ONCE,
            next_run=schedule_time
        )
        
        return task_id, True
        
    except Exception as e:
        logger.error(f"❌ Failed to queue Amazon search task for '{search_term}': {str(e)}", exc_info=True)
        return None, False

def check_stalled_search_task(task_id, search_term):
    """
    Safety check for stalled search tasks
    """
    logger.info(f"🔍 Safety check for search task {task_id} (term: '{search_term}')")
    
    try:
        redis_kwargs = get_redis_connection()
        r = redis.Redis(**redis_kwargs)
        
        # Check if task is still pending
        pending_task = r.get(f"pending_search_task:{task_id}")
        if pending_task:
            logger.warning(f"⚠️ Search task {task_id} appears stalled after 1 hour")
            
            # Check if result exists
            result = r.get(f"search_result:{task_id}")
            if not result:
                logger.warning(f"⚠️ No result found for stalled search task {task_id}")
                # Could implement retry logic here if needed
                
                # Store error result for any clients polling
                error_data = {
                    "status": "error",
                    "error": "Search task timed out after 1 hour",
                    "searchTerm": search_term,
                    "timestamp": timezone.now().isoformat()
                }
                r.set(f"search_result:{task_id}", json.dumps(error_data), ex=3600)
                
        else:
            logger.info(f"✅ Search task {task_id} completed (no longer pending)")
            
    except Exception as e:
        logger.error(f"❌ Error in safety check for search task {task_id}: {str(e)}")

def generate_affiliate_from_search(task_id, search_term, search_key):
    """
    Generate an affiliate link based on a product search term.
    This will search Amazon for the product and create an affiliate link.
    """
    logger = logging.getLogger('affiliate_tasks')
    logger.info(f"Generating affiliate from search: '{search_term}', key: '{search_key}'")
    
    try:
        # Use the Amazon search API or puppeteer to find the product
        # For now, we'll just create a direct search URL
        import urllib.parse
        encoded_search = urllib.parse.quote(search_term)
        
        # This URL will redirect to Amazon search results
        search_url = f"https://www.amazon.com/s?k={encoded_search}"
        
        # Generate affiliate link using the search URL
        result = generate_standalone_amazon_affiliate_url(search_url)
        
        logger.info(f"Generated affiliate link for search: {result}")
        return result
    except Exception as e:
        logger.error(f"Error generating affiliate from search: {str(e)}")
        
        # Store error in Redis
        import redis
        import json
        from django.conf import settings
        
        redis_kwargs = {
            'host': getattr(settings, 'REDIS_HOST', 'localhost'),
            'port': getattr(settings, 'REDIS_PORT', 6379),
            'decode_responses': True
        }
        if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
            redis_kwargs['password'] = settings.REDIS_PASSWORD
            
        r = redis.Redis(**redis_kwargs)
        r.set(f"standalone_task_status:{task_id}", json.dumps({
            "status": "error",
            "message": str(e),
            "url": None
        }), ex=86400)
        
        return None

def requeue_pending_affiliate_links(platform=None, limit=None):
    """
    Find all AffiliateLinks with empty affiliate_url or error messages and resubmit them to the queue
    
    Args:
        platform (str, optional): Filter by platform (e.g., 'amazon')
        limit (int, optional): Limit number of links to process
    
    Returns:
        dict: Results summary with counts
    """
    logger.info(f"Starting requeue_pending_affiliate_links: platform={platform}, limit={limit}")
    
    # Find all affiliate links with empty affiliate URLs or error messages
    queryset = AffiliateLink.objects.filter(
        models.Q(affiliate_url='') | 
        models.Q(affiliate_url__startswith='ERROR:')
    )
    
    if platform:
        queryset = queryset.filter(platform=platform)
    
    total_count = queryset.count()
    logger.info(f"Found {total_count} affiliate links to requeue")
    
    if limit:
        queryset = queryset[:limit]
        logger.info(f"Processing only {limit} links due to limit parameter")
    
    success_count = 0
    error_count = 0
    
    for link in queryset:
        try:
            logger.info(f"Requeuing affiliate link {link.id} for {link.platform} with platform_id {link.platform_id}")
            
            if link.platform == 'amazon':
                # Use our new webhook-based generation function
                result = generate_amazon_affiliate_url(link.id, link.platform_id)
                
                if result:
                    success_count += 1
                    # Update note to indicate requeuing
                    link.notes = f"Requeued on {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    link.save(update_fields=['notes'])
                else:
                    error_count += 1
            else:
                logger.warning(f"Unsupported platform: {link.platform}")
                error_count += 1
                
        except Exception as e:
            logger.error(f"Error requeuing affiliate link {link.id}: {str(e)}", exc_info=True)
            error_count += 1
    
    results = {
        "total_found": total_count,
        "processed": success_count + error_count,
        "success": success_count,
        "errors": error_count
    }
    
    logger.info(f"Completed requeue_pending_affiliate_links: {results}")
    return results

class Command(BaseCommand):
    help = 'Clear problematic scheduled tasks that are causing invalid decimal literal errors'

    def handle(self, *args, **options):
        # Delete all safety check tasks
        count = Schedule.objects.filter(func='affiliates.tasks.check_stalled_affiliate_task').delete()[0]
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} problematic scheduled tasks'))
        logger.info(f'Deleted {count} problematic scheduled tasks')