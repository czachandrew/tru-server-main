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
    
    def resolve_full_name(self, info):
        return self.get_full_name()
    
    def resolve_has_google_account(self, info):
        return bool(self.google_id)
    
    def resolve_wallet(self, info):
        try:
            return float(self.profile.wallet)
        except (UserProfile.DoesNotExist, AttributeError):
            return 0.0

class UserProfileType(DjangoObjectType):
    class Meta:
        model = UserProfile
        fields = '__all__'