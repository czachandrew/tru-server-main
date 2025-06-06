import graphene
from django.contrib.auth import get_user_model
from graphql import GraphQLError
from graphql_jwt.shortcuts import get_token, create_refresh_token
from ..types.user import UserType
from ecommerce_platform.services.google_oauth import GoogleOAuthService
from users.models import UserProfile
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

class GoogleOAuthLogin(graphene.Mutation):
    """
    Mutation for logging in with Google OAuth using access token
    """
    class Arguments:
        access_token = graphene.String(required=True, description="Google access token")
    
    # Return fields
    success = graphene.Boolean()
    user = graphene.Field(UserType)
    token = graphene.String()
    refresh_token = graphene.String()
    refreshToken = graphene.String()  # Alias for compatibility
    message = graphene.String()
    is_new_user = graphene.Boolean()
    
    def mutate(self, info, access_token):
        try:
            # Verify access token by calling Google's API
            user_info = GoogleOAuthService.get_user_info_from_access_token(access_token)
            
            if not user_info:
                raise GraphQLError(
                    "Invalid Google access token",
                    extensions={"code": "INVALID_CREDENTIALS"}
                )
            
            # Check if email is verified
            if not user_info.get('email_verified', False):
                raise GraphQLError(
                    "Email not verified with Google",
                    extensions={"code": "EMAIL_NOT_VERIFIED"}
                )
            
            email = user_info['email']
            google_id = user_info['google_id']
            
            # Check if user exists
            user = None
            is_new_user = False
            
            # First try to find by Google ID
            try:
                user = User.objects.get(google_id=google_id)
                logger.info(f"Found existing user by Google ID: {email}")
            except User.DoesNotExist:
                # Try to find by email
                try:
                    user = User.objects.get(email=email)
                    # Update existing user with Google ID
                    user.google_id = google_id
                    if user_info.get('avatar'):
                        user.avatar = user_info['avatar']
                    user.save()
                    logger.info(f"Linked Google account to existing user: {email}")
                except User.DoesNotExist:
                    # Create new user
                    user = User.objects.create_user(
                        email=email,
                        google_id=google_id,
                        first_name=user_info.get('first_name', ''),
                        last_name=user_info.get('last_name', ''),
                        avatar=user_info.get('avatar', '')
                    )
                    is_new_user = True
                    logger.info(f"Created new user: {email}")
                    
                    # Create user profile
                    UserProfile.objects.create(user=user)
            
            # Generate JWT tokens
            token = get_token(user)
            refresh_token = create_refresh_token(user)
            
            message = "Login successful"
            if is_new_user:
                message = "Account created and login successful"
            
            logger.info(f"Google OAuth login successful for: {email}")
            
            return GoogleOAuthLogin(
                success=True,
                user=user,
                token=token,
                refresh_token=refresh_token,
                refreshToken=refresh_token,
                message=message,
                is_new_user=is_new_user
            )
            
        except GraphQLError:
            raise
        except Exception as e:
            logger.error(f"Google OAuth login error: {e}")
            raise GraphQLError(
                f"Authentication failed: {str(e)}",
                extensions={"code": "AUTHENTICATION_FAILED"}
            )


class GoogleOAuthRegister(graphene.Mutation):
    """
    Mutation for registering with Google OAuth using access token
    """
    class Arguments:
        access_token = graphene.String(required=True, description="Google access token")
    
    # Return fields
    success = graphene.Boolean()
    user = graphene.Field(UserType)
    token = graphene.String()
    refresh_token = graphene.String()
    refreshToken = graphene.String()
    message = graphene.String()
    
    def mutate(self, info, access_token):
        try:
            # Verify access token by calling Google's API
            user_info = GoogleOAuthService.get_user_info_from_access_token(access_token)
            
            if not user_info:
                raise GraphQLError(
                    "Invalid Google access token",
                    extensions={"code": "INVALID_CREDENTIALS"}
                )
            
            email = user_info['email']
            google_id = user_info['google_id']
            
            # Check if user already exists
            if User.objects.filter(email=email).exists():
                raise GraphQLError(
                    "User with this email already exists. Please use login instead.",
                    extensions={"code": "USER_EXISTS"}
                )
            
            if User.objects.filter(google_id=google_id).exists():
                raise GraphQLError(
                    "Google account already registered. Please use login instead.",
                    extensions={"code": "GOOGLE_ACCOUNT_EXISTS"}
                )
            
            # Create new user
            user = User.objects.create_user(
                email=email,
                google_id=google_id,
                first_name=user_info.get('first_name', ''),
                last_name=user_info.get('last_name', ''),
                avatar=user_info.get('avatar', '')
            )
            
            # Create user profile
            UserProfile.objects.create(user=user)
            
            # Generate JWT tokens
            token = get_token(user)
            refresh_token = create_refresh_token(user)
            
            logger.info(f"Google OAuth registration successful for: {email}")
            
            return GoogleOAuthRegister(
                success=True,
                user=user,
                token=token,
                refresh_token=refresh_token,
                refreshToken=refresh_token,
                message="Account created successfully"
            )
            
        except GraphQLError:
            raise
        except Exception as e:
            logger.error(f"Google OAuth registration error: {e}")
            raise GraphQLError(
                f"Registration failed: {str(e)}",
                extensions={"code": "REGISTRATION_FAILED"}
            )


class LinkGoogleAccount(graphene.Mutation):
    """
    Mutation for linking Google account to existing user
    """
    class Arguments:
        access_token = graphene.String(required=True, description="Google access token")
    
    success = graphene.Boolean()
    user = graphene.Field(UserType)
    message = graphene.String()
    
    def mutate(self, info, access_token):
        # Ensure user is authenticated
        if not info.context.user.is_authenticated:
            raise GraphQLError(
                "Authentication required",
                extensions={"code": "AUTHENTICATION_REQUIRED"}
            )
        
        try:
            # Verify access token by calling Google's API
            user_info = GoogleOAuthService.get_user_info_from_access_token(access_token)
            
            if not user_info:
                raise GraphQLError(
                    "Invalid Google access token",
                    extensions={"code": "INVALID_CREDENTIALS"}
                )
            
            google_id = user_info['google_id']
            google_email = user_info['email']
            
            # Check if Google account is already linked to another user
            if User.objects.filter(google_id=google_id).exists():
                raise GraphQLError(
                    "This Google account is already linked to another user",
                    extensions={"code": "GOOGLE_ACCOUNT_LINKED"}
                )
            
            # Verify email matches (optional security check)
            user = info.context.user
            if user.email != google_email:
                raise GraphQLError(
                    "Google account email must match your account email",
                    extensions={"code": "EMAIL_MISMATCH"}
                )
            
            # Link Google account
            user.google_id = google_id
            if user_info.get('avatar'):
                user.avatar = user_info['avatar']
            user.save()
            
            logger.info(f"Google account linked successfully for: {user.email}")
            
            return LinkGoogleAccount(
                success=True,
                user=user,
                message="Google account linked successfully"
            )
            
        except GraphQLError:
            raise
        except Exception as e:
            logger.error(f"Link Google account error: {e}")
            raise GraphQLError(
                f"Failed to link Google account: {str(e)}",
                extensions={"code": "LINK_FAILED"}
            ) 