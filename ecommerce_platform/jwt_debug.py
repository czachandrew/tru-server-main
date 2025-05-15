import logging
import traceback
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from graphql_jwt.settings import jwt_settings
from graphql_jwt.shortcuts import get_user_by_token

logger = logging.getLogger(__name__)
User = get_user_model()

def get_http_authorization(request):
    """Get HTTP authorization from Django request."""
    auth = request.META.get('HTTP_AUTHORIZATION', '').split()
    prefix = jwt_settings.JWT_AUTH_HEADER_PREFIX.lower()

    if len(auth) != 2 or auth[0].lower() != prefix:
        return None
    return auth[1]

class DebugJSONWebTokenBackend:
    def authenticate(self, request=None, **kwargs):
        if request is None:
            return None

        token = get_http_authorization(request)
        if token is None:
            logger.warning("🔴 No token in request")
            return None

        try:
            logger.info(f"🟢 Attempting to validate token: {token[:10]}...")
            
            # First try our manual decode
            try:
                raw_payload = jwt.decode(
                    token, 
                    settings.SECRET_KEY,
                    algorithms=['HS256'],
                    options={'verify_signature': True}
                )
                logger.info(f"✅ Successfully decoded JWT: {raw_payload}")
                
                # Try to get user directly
                user_id = raw_payload.get('user_id')
                if user_id:
                    try:
                        user = User.objects.get(id=user_id)
                        logger.info(f"✅ Found user via direct ID lookup: {user.email}")
                        return user
                    except User.DoesNotExist:
                        logger.error(f"❌ User ID {user_id} from token not found in DB")
            except Exception as e:
                logger.error(f"❌ Manual decode failed: {str(e)}")
                logger.error(traceback.format_exc())
            
            # Now try the standard library way
            try:
                user = get_user_by_token(token)
                logger.info(f"✅ Standard library get_user_by_token succeeded: {user.email}")
                return user
            except Exception as e:
                logger.error(f"❌ Standard get_user_by_token failed: {str(e)}")
                logger.error(traceback.format_exc())
                
            return None
        except Exception as e:
            logger.error(f"❌ JWT authentication failed: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None 