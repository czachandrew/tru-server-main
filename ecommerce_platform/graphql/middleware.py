import time
import logging
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)

class ResolverTimingMiddleware:
    def resolve(self, next, root, info, **args):
        start_time = time.time()
        logger.debug(f"Resolving: {info.path} with args: {args}")
        
        try:
            return_value = next(root, info, **args)
            duration = time.time() - start_time
            logger.debug(f"Resolved: {info.path} in {duration:.4f}s")
            return return_value
        except Exception as error:
            duration = time.time() - start_time
            logger.error(f"Error in resolver {info.path} after {duration:.4f}s: {str(error)}")
            raise 

class DebugAuthMiddleware:
    def resolve(self, next, root, info, **args):
        logger.info(f"DebugAuthMiddleware: Path = {info.path}")
        logger.info(f"DebugAuthMiddleware: Auth = {info.context.user.is_authenticated}")
        
        if info.context.user.is_authenticated:
            logger.info(f"DebugAuthMiddleware: User ID = {info.context.user.id}")
        
        auth_header = info.context.META.get('HTTP_AUTHORIZATION', '')
        if auth_header:
            logger.info(f"DebugAuthMiddleware: Auth header present = {auth_header[:15]}...")
        
        return next(root, info, **args) 