import graphene
from graphene_django import DjangoObjectType
from django.contrib.auth import get_user_model
from users.models import UserProfile

User = get_user_model()

class UserType(DjangoObjectType):
    wallet = graphene.Float()
    
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'is_active', 'date_joined')
    
    def resolve_wallet(self, info):
        try:
            return self.profile.wallet
        except UserProfile.DoesNotExist:
            return 0

class UserProfileType(DjangoObjectType):
    class Meta:
        model = UserProfile
        fields = "__all__"