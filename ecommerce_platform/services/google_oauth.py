import requests
from django.conf import settings
import logging
import json
import os

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
    def get_allowed_client_ids():
        """
        Get list of allowed Google OAuth client IDs
        Supports multiple clients (Chrome extension, iOS app, etc.)
        """
        # Get all client IDs from settings
        client_ids_str = getattr(settings, 'GOOGLE_OAUTH_CLIENT_IDS', None)
        
        logger.info(f"Raw GOOGLE_OAUTH_CLIENT_IDS from settings: '{client_ids_str}'")
        
        if not client_ids_str:
            logger.error("No Google OAuth client IDs configured")
            return []
        
        # Split by comma and clean up whitespace
        client_ids = [cid.strip() for cid in client_ids_str.split(',') if cid.strip()]
        
        logger.info(f"Parsed Google OAuth client IDs: {client_ids}")
        logger.info(f"Number of client IDs configured: {len(client_ids)}")
        
        return client_ids
    
    @staticmethod
    def verify_google_token(token):
        """
        Verify Google ID token and return user info
        """
        if not GOOGLE_AUTH_AVAILABLE:
            logger.error("Google Auth libraries not available")
            return None
            
        try:
            # Get all allowed client IDs
            allowed_client_ids = GoogleOAuthService.get_allowed_client_ids()
            
            if not allowed_client_ids:
                logger.error("No Google OAuth client IDs configured")
                return None
            
            logger.info(f"Attempting to verify Google token with {len(allowed_client_ids)} client IDs")
            
            # Try to verify with each client ID
            for i, client_id in enumerate(allowed_client_ids):
                logger.info(f"Trying client ID {i+1}/{len(allowed_client_ids)}: {client_id[:20]}...")
                
                try:
                    # Verify the token with Google
                    idinfo = id_token.verify_oauth2_token(
                        token, 
                        google_requests.Request(),
                        client_id
                    )
                    
                    logger.info(f"Token verification successful with client ID {i+1}")
                    
                    # Verify the issuer
                    if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                        logger.warning(f"Wrong issuer for client ID {i+1}: {idinfo['iss']}")
                        continue  # Try next client ID
                    
                    # Extract user information
                    user_info = {
                        'google_id': idinfo['sub'],
                        'email': idinfo['email'],
                        'first_name': idinfo.get('given_name', ''),
                        'last_name': idinfo.get('family_name', ''),
                        'avatar': idinfo.get('picture', ''),
                        'email_verified': idinfo.get('email_verified', False)
                    }
                    
                    logger.info(f"Successfully verified Google token with client ID: {client_id[:20]}...")
                    logger.info(f"User email: {user_info['email']}")
                    return user_info
                    
                except ValueError as e:
                    logger.warning(f"Token verification failed with client ID {i+1} ({client_id[:20]}...): {e}")
                    continue  # Try next client ID
                except Exception as e:
                    logger.error(f"Unexpected error with client ID {i+1}: {e}")
                    continue  # Try next client ID
            
            # If we get here, no client ID worked
            logger.error("Google token verification failed with all client IDs")
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error during Google token verification: {e}")
            return None
    
    @staticmethod
    def detect_token_type(token):
        """
        Detect whether the token is an ID token (JWT) or access token
        """
        if not token:
            return None
            
        # ID tokens are JWTs with 3 parts separated by dots
        if token.count('.') == 2:
            logger.info("Token appears to be an ID token (JWT format)")
            return "id_token"
        
        # Access tokens typically start with 'ya29.' and are single strings
        elif token.startswith('ya29.'):
            logger.info("Token appears to be an access token (ya29. prefix)")
            return "access_token"
        
        else:
            logger.warning(f"Unknown token format: {token[:20]}...")
            return "unknown"
    
    @staticmethod
    def get_user_info_from_token(token):
        """
        Universal method to get user info from either ID token or access token
        """
        if not token:
            logger.error("No token provided")
            return None
            
        logger.info(f"Processing token: {token[:20]}...")
        logger.info(f"Token length: {len(token)} characters")
        
        # Detect token type
        token_type = GoogleOAuthService.detect_token_type(token)
        
        if token_type == "id_token":
            logger.info("Processing as ID token")
            return GoogleOAuthService.verify_google_token(token)
        elif token_type == "access_token":
            logger.info("Processing as access token")
            return GoogleOAuthService.get_user_info_from_access_token(token)
        else:
            logger.error(f"Unsupported token type: {token_type}")
            return None
    
    @staticmethod
    def get_user_info_from_access_token(access_token):
        """
        Get user info from Google using access token
        Primary method for Chrome extensions and mobile apps
        """
        if not access_token:
            logger.error("No access token provided")
            return None
            
        try:
            logger.info(f"Verifying Google access token: {access_token[:20]}...")
            logger.info(f"Access token length: {len(access_token)} characters")
            
            # Call Google's userinfo endpoint
            response = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10  # Add timeout
            )
            
            logger.info(f"Google API response status: {response.status_code}")
            logger.info(f"Google API response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Successfully verified Google user: {user_data.get('email')}")
                logger.info(f"Full Google API response: {json.dumps(user_data, indent=2)}")
                
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
                logger.error(f"Google API error response: {response.text}")
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
            logger.warning("No access token provided for validation")
            return False
        
        logger.info(f"Validating access token format: {access_token[:20]}...")
        logger.info(f"Access token length: {len(access_token)} characters")
        
        # Google access tokens typically start with 'ya29.' and are quite long
        # But some tokens might have different formats, so we'll be more lenient
        if len(access_token) < 50:  # Minimum reasonable length
            logger.warning(f"Access token too short: {len(access_token)} characters")
            return False
            
        logger.info("Access token format validation passed")
        return True 