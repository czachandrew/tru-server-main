from datetime import datetime
from calendar import timegm
from graphql_jwt.settings import jwt_settings
import redis
import logging
from django.conf import settings
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def jwt_payload(user, context=None):
    username = user.get_username()
    
    # Get expiration time as a timestamp (integer)
    expiration = datetime.utcnow() + jwt_settings.JWT_EXPIRATION_DELTA
    exp_timestamp = timegm(expiration.utctimetuple())
    
    # Get current time as a timestamp
    orig_iat_timestamp = timegm(datetime.utcnow().utctimetuple())
    
    payload = {
        'username': username,
        'exp': exp_timestamp,  # Use timestamp instead of datetime object
        'orig_iat': orig_iat_timestamp,  # Use timestamp instead of datetime object
        'user_id': str(user.id),
    }
    
    if jwt_settings.JWT_AUDIENCE is not None:
        payload['aud'] = jwt_settings.JWT_AUDIENCE
    
    if jwt_settings.JWT_ISSUER is not None:
        payload['iss'] = jwt_settings.JWT_ISSUER
    
    return payload

# Function to get Redis connection parameters
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
            'host': getattr(settings, 'REDIS_HOST', 'localhost'),
            'port': getattr(settings, 'REDIS_PORT', 6379),
            'decode_responses': True
        }
        if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
            redis_kwargs['password'] = settings.REDIS_PASSWORD
        return redis_kwargs

def clear_redis_tasks():
    """
    Clear all affiliate link tasks from Redis
    """
    logger.info("Clearing all affiliate link tasks from Redis")
    
    try:
        redis_kwargs = get_redis_connection()
        r = redis.Redis(**redis_kwargs)
        
        # Get all keys related to affiliate tasks
        pending_keys = r.keys('pending_standalone_task:*')
        status_keys = r.keys('standalone_task_status:*')
        search_keys = r.keys('pending_search_term:*')
        
        # Count total keys to delete
        total_keys = len(pending_keys) + len(status_keys) + len(search_keys)
        logger.info(f"Found {total_keys} Redis keys to delete")
        
        # Delete all keys
        if pending_keys:
            r.delete(*pending_keys)
        if status_keys:
            r.delete(*status_keys)
        if search_keys:
            r.delete(*search_keys)
        
        logger.info(f"Successfully cleared {total_keys} Redis keys")
        
        return total_keys
    except Exception as e:
        logger.error(f"Error clearing Redis tasks: {str(e)}")
        return 0