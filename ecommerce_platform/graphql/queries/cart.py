import graphene
from store.models import Cart
from ..types import CartType

class CartQuery(graphene.ObjectType):
    cart = graphene.Field(CartType, id=graphene.ID(), session_id=graphene.String())
    
    def resolve_cart(self, info, id=None, session_id=None):
        user = info.context.user
        
        if id:
            return Cart.objects.get(pk=id)
        
        if session_id:
            return Cart.objects.filter(session_id=session_id).first()
        
        if user.is_authenticated:
            return Cart.objects.filter(user=user).first()
        
        return None 