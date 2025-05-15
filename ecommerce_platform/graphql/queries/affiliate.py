import graphene
from affiliates.models import AffiliateLink
from ..types import AffiliateLinkType
import logging
import redis
import json
from django.conf import settings

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

class AffiliateQuery(graphene.ObjectType):
    affiliate_links = graphene.List(AffiliateLinkType, product_id=graphene.ID(required=True))
    check_affiliate_task = graphene.JSONString(task_id=graphene.String(required=True))
    
    def resolve_affiliate_links(self, info, product_id):
        return AffiliateLink.objects.filter(product_id=product_id)

    def resolve_check_affiliate_task(self, info, task_id):
        """Check status of an affiliate link generation task"""
        logger = logging.getLogger('affiliate_tasks')
        logger.info(f"Checking affiliate task status for: {task_id}")
        
        redis_kwargs = get_redis_kwargs()
        r = redis.Redis(**redis_kwargs)
        
        # Check if task is still pending
        asin = r.get(f"pending_standalone_task:{task_id}")
        if asin:
            return {
                "status": "processing",
                "message": "Task is still being processed"
            }
        
        # Check if results are available
        result_json = r.get(f"standalone_task_status:{task_id}")
        if result_json:
            return json.loads(result_json)
        
        return {
            "status": "not_found",
            "message": "Task not found or expired"
        } 