import logging

logger = logging.getLogger(__name__)

class ResponseSizeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        if request.path == '/graphql/':
            content_length = len(response.content) if hasattr(response, 'content') else 0
            logger.info(f"GraphQL Response Size: {content_length} bytes")
            
            # Log first 200 chars of response for debugging
            if hasattr(response, 'content'):
                preview = response.content[:200].decode('utf-8', errors='ignore')
                logger.info(f"Response Preview: {preview}")
        
        return response 