import graphene
from graphene_django import DjangoObjectType
from django.contrib.auth import get_user_model
from users.models import UserProfile

User = get_user_model()

class UserType(DjangoObjectType):
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'is_active', 
                 'is_staff', 'date_joined', 'google_id', 'avatar')
    
    # Add computed fields
    full_name = graphene.String()
    has_google_account = graphene.Boolean()
    wallet = graphene.Float()
    profile = graphene.Field('ecommerce_platform.graphql.types.user.UserProfileType')
    
    def resolve_full_name(self, info):
        return self.get_full_name()
    
    def resolve_has_google_account(self, info):
        return bool(self.google_id)
    
    def resolve_wallet(self, info):
        try:
            return float(self.profile.wallet)
        except (UserProfile.DoesNotExist, AttributeError):
            return 0.0
    
    def resolve_profile(self, info):
        try:
            return self.profile
        except UserProfile.DoesNotExist:
            return None

class UserProfileType(DjangoObjectType):
    class Meta:
        model = UserProfile
        fields = ('id', 'user', 'phone', 'company', 'preferred_categories', 'created_at', 'updated_at',
                 'stripe_connect_account_id', 'preferred_payout_method', 'paypal_email', 'payout_status',
                 'last_payout_at', 'available_balance', 'pending_balance', 'lifetime_earnings',
                 'total_withdrawn', 'total_spent', 'activity_score', 'min_cashout_amount', 'wallet',
                 'is_organization', 'organization_type', 'organization_name', 'min_payout_amount')