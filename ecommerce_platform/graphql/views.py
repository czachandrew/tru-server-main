import json
import logging
import jwt
from graphene_django.views import GraphQLView
from django.conf import settings

logger = logging.getLogger(__name__)

class DebugGraphQLView(GraphQLView):
    def dispatch(self, request, *args, **kwargs):
        logger.info(f"GraphQL request received: {request.method}")
        
        # Log headers (excluding sensitive ones)
        safe_headers = {k: v for k, v in request.headers.items() 
                        if k.lower() not in ('authorization', 'cookie')}
        logger.info(f"Request headers: {safe_headers}")
        
        # Debug JWT token if present
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('JWT '):
            token = auth_header.split(' ')[1]
            try:
                # Log decoded token (excluding signature)
                decoded = jwt.decode(
                    token, 
                    settings.SECRET_KEY,
                    options={"verify_signature": False},
                    algorithms=['HS256']
                )
                logger.info(f"Decoded JWT payload: {decoded}")
            except Exception as e:
                logger.error(f"Error decoding JWT: {str(e)}")
        
        # Log body for POST requests
        if request.method == 'POST' and request.body:
            try:
                body = json.loads(request.body)
                # Don't log variables as they might contain sensitive data
                safe_body = {k: v for k, v in body.items() if k != 'variables'}
                
                # Log variables securely (excluding passwords)
                if 'variables' in body and body['variables']:
                    safe_vars = {k: v for k, v in body['variables'].items() 
                                if k.lower() not in ('password', 'current_password')}
                    if safe_vars:
                        logger.info(f"Request variables: {safe_vars}")
                
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