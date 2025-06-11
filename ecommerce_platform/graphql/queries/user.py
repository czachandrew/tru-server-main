import graphene
from django.contrib.auth import get_user_model
from ..types.user import UserType

User = get_user_model()

class UserQuery(graphene.ObjectType):
    me = graphene.Field(UserType, description="Get the authenticated user's information")
    user = graphene.Field(UserType, id=graphene.ID())
    users = graphene.List(UserType)  # Optional: get all users
    current_user = graphene.Field(UserType)
    
    def resolve_me(self, info):
        user = info.context.user
        if user.is_anonymous:
            return None
        return user
    
    def resolve_current_user(self, info):
        if info.context.user.is_authenticated:
            return info.context.user
        return None
    
    def resolve_user(self, info, id=None):
        if id:
            try:
                return User.objects.get(pk=id)
            except User.DoesNotExist:
                return None
        return None
    
    def resolve_users(self, info):
        # Only staff/admin can query all users
        if info.context.user.is_authenticated and info.context.user.is_staff:
            return User.objects.all()
        return [] 