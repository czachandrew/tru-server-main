import time
import logging

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