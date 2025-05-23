import graphene
from graphene_django import DjangoObjectType
from store.models import Cart, CartItem
from django.contrib.auth.models import User
from .user import UserType
class CartType(DjangoObjectType):
    class Meta:
        model = Cart
        fields = "__all__"
    
    total_items = graphene.Int()
    total_price = graphene.Float()
    
    def resolve_total_items(self, info):
        return sum(item.quantity for item in self.items.all())
    
    def resolve_total_price(self, info):
        return sum(item.quantity * item.offer.selling_price for item in self.items.all())

class CartItemType(DjangoObjectType):
    class Meta:
        model = CartItem
        fields = "__all__"
    
    total_price = graphene.Float()
    
    def resolve_total_price(self, info):
        return self.quantity * self.offer.selling_price
