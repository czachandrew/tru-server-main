import graphene
import graphql_jwt
import json
from django.contrib.auth import get_user_model
from graphql_jwt.decorators import login_required
from graphql_jwt.shortcuts import get_token, create_refresh_token
from ..types.user import UserType
from graphql import GraphQLError

User = get_user_model()

class ObtainJSONWebToken(graphql_jwt.JSONWebTokenMutation):
    user = graphene.Field(UserType)
    refresh_token = graphene.String()
    refreshToken = graphene.String()
    
    class Meta:
        name = 'ObtainJSONWebToken'
        description = 'Obtain JSON Web Token mutation'

    @classmethod
    def resolve(cls, root, info, **kwargs):
        user = info.context.user
        refresh_token = create_refresh_token(user)
        return cls(
            user=user, 
            refresh_token=refresh_token,
            refreshToken=refresh_token
        )
    
class Register(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)
        password = graphene.String(required=True)
        first_name = graphene.String()
        last_name = graphene.String()
    
    success = graphene.Boolean()
    user = graphene.Field(UserType)
    
    def mutate(self, info, email, password, first_name="", last_name=""):
        if User.objects.filter(email=email).exists():
            raise Exception("User with this email already exists")
            
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        
        return Register(success=True, user=user)

class AuthMutation(graphene.ObjectType):
    register = Register.Field()
    token_auth = ObtainJSONWebToken.Field()
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field() 