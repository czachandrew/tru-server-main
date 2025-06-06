import requests
from django.conf import settings
import logging
import json

logger = logging.getLogger(__name__)

try:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    logger.warning("Google Auth libraries not installed. Google OAuth will not be available.")
    GOOGLE_AUTH_AVAILABLE = False

class GoogleOAuthService:
    """Service for handling Google OAuth verification"""
    
    @staticmethod
    def verify_google_token(token):
        """
        Verify Google ID token and return user info
        """
        if not GOOGLE_AUTH_AVAILABLE:
            logger.error("Google Auth libraries not available")
            return None
            
        try:
            # Verify the token with Google
            idinfo = id_token.verify_oauth2_token(
                token, 
                google_requests.Request(),
                settings.GOOGLE_OAUTH_CLIENT_ID
            )
            
            # Verify the issuer
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')
            
            # Extract user information
            user_info = {
                'google_id': idinfo['sub'],
                'email': idinfo['email'],
                'first_name': idinfo.get('given_name', ''),
                'last_name': idinfo.get('family_name', ''),
                'avatar': idinfo.get('picture', ''),
                'email_verified': idinfo.get('email_verified', False)
            }
            
            return user_info
            
        except ValueError as e:
            logger.error(f"Google token verification failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during Google token verification: {e}")
            return None
    
    @staticmethod
    def get_user_info_from_access_token(access_token):
        """
        Get user info from Google using access token
        Primary method for Chrome extensions
        """
        if not access_token:
            logger.error("No access token provided")
            return None
            
        try:
            logger.info(f"Verifying Google access token: {access_token[:20]}...")
            
            # Call Google's userinfo endpoint
            response = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10  # Add timeout
            )
            
            logger.info(f"Google API response status: {response.status_code}")
            
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Successfully verified Google user: {user_data.get('email')}")
                
                # Validate required fields
                required_fields = ['id', 'email']
                for field in required_fields:
                    if field not in user_data:
                        logger.error(f"Missing required field '{field}' in Google response")
                        return None
                
                return {
                    'google_id': user_data['id'],
                    'email': user_data['email'],
                    'first_name': user_data.get('given_name', ''),
                    'last_name': user_data.get('family_name', ''),
                    'avatar': user_data.get('picture', ''),
                    'email_verified': user_data.get('verified_email', False)
                }
            
            elif response.status_code == 401:
                logger.error("Google access token is invalid or expired")
                return None
            
            else:
                logger.error(f"Google API error: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Timeout while verifying Google access token")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error while verifying Google access token: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Google: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error verifying Google access token: {e}")
            return None
    
    @staticmethod
    def validate_access_token(access_token):
        """
        Validate access token format before making API call
        """
        if not access_token:
            return False
        
        # Google access tokens typically start with 'ya29.' and are quite long
        if not access_token.startswith('ya29.') or len(access_token) < 100:
            logger.warning(f"Access token format looks suspicious: {access_token[:20]}...")
            return False
            
        return True 