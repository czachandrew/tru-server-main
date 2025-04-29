import json
import logging
from graphene_django.views import GraphQLView

logger = logging.getLogger(__name__)

class DebugGraphQLView(GraphQLView):
    def dispatch(self, request, *args, **kwargs):
        logger.info(f"GraphQL request received: {request.method}")
        
        # Log headers (excluding sensitive ones)
        safe_headers = {k: v for k, v in request.headers.items() 
                        if k.lower() not in ('authorization', 'cookie')}
        logger.info(f"Request headers: {safe_headers}")
        
        # Log body for POST requests
        if request.method == 'POST' and request.body:
            try:
                body = json.loads(request.body)
                # Don't log variables as they might contain sensitive data
                safe_body = {k: v for k, v in body.items() if k != 'variables'}
                logger.info(f"Request body: {safe_body}")
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in request body: {request.body[:200]}")
        
        try:
            response = super().dispatch(request, *args, **kwargs)
            logger.info(f"Response status: {response.status_code}")
            
            # Log error responses
            if response.status_code >= 400:
                try:
                    content = json.loads(response.content)
                    logger.error(f"GraphQL error response: {content}")
                except Exception as e:
                    logger.error(f"Error parsing response content: {str(e)}")
            
            return response
        except Exception as e:
            logger.exception(f"Exception in GraphQL view: {str(e)}")
            raise 