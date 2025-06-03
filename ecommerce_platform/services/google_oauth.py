import requests
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class GoogleOAuthService:
    """Service for handling Google OAuth verification"""
    
    @staticmethod
    def verify_google_token(token):
        """
        Verify Google ID token and return user info
        """
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
        Alternative method if ID token is not available
        """
        try:
            response = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {access_token}'}
            )
            
            if response.status_code == 200:
                user_data = response.json()
                return {
                    'google_id': user_data['id'],
                    'email': user_data['email'],
                    'first_name': user_data.get('given_name', ''),
                    'last_name': user_data.get('family_name', ''),
                    'avatar': user_data.get('picture', ''),
                    'email_verified': user_data.get('verified_email', False)
                }
            else:
                logger.error(f"Failed to get user info from Google: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting user info from Google: {e}")
            return None 