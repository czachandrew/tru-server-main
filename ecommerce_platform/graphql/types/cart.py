import graphene
from graphene_django import DjangoObjectType
from store.models import Cart, CartItem
from django.contrib.auth.models import User

class CartItemType(DjangoObjectType):
    total_price = graphene.Float()
    
    class Meta:
        model = CartItem
        fields = (
            "id", "cart", "offer", "quantity", "added_at", "updated_at"
        )
    
    def resolve_total_price(self, info):
        return self.quantity * self.offer.selling_price

class CartType(DjangoObjectType):
    total_items = graphene.Int()
    total_price = graphene.Float()
    
    class Meta:
        model = Cart
        fields = (
            "id", "user", "session_id", "items", "created_at", "updated_at"
        )
    
    def resolve_total_items(self, info):
        return sum(item.quantity for item in self.items.all())
    
    def resolve_total_price(self, info):
        return sum(item.quantity * item.offer.selling_price for item in self.items.all())

class UserType(DjangoObjectType):
    class Meta:
        model = User
        fields = ("id", "username", "email") 