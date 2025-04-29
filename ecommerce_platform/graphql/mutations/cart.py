import graphene
from graphql import GraphQLError
import uuid
from store.models import Cart, CartItem
from offers.models import Offer
from ..types import CartType, CartItemType

class CartItemInput(graphene.InputObjectType):
    offer_id = graphene.ID(required=True)
    quantity = graphene.Int(required=True)

class AddToCart(graphene.Mutation):
    class Arguments:
        session_id = graphene.String()
        cart_id = graphene.ID()
        item = CartItemInput(required=True)
    
    cart = graphene.Field(CartType)
    
    @staticmethod
    def mutate(root, info, item, session_id=None, cart_id=None):
        try:
            # Get or create cart
            cart = None
            user = info.context.user
            
            if cart_id:
                cart = Cart.objects.get(pk=cart_id)
            elif session_id:
                cart, created = Cart.objects.get_or_create(
                    session_id=session_id,
                    defaults={'user': user if user.is_authenticated else None}
                )
            elif user.is_authenticated:
                cart, created = Cart.objects.get_or_create(
                    user=user,
                    defaults={'session_id': ''}
                )
            else:
                # Generate new session ID if needed
                new_session_id = str(uuid.uuid4())
                cart = Cart.objects.create(session_id=new_session_id)
            
            # Get the offer
            offer = Offer.objects.get(pk=item.offer_id)
            
            # Check if item already in cart
            try:
                cart_item = CartItem.objects.get(cart=cart, offer=offer)
                cart_item.quantity += item.quantity
                cart_item.save()
            except CartItem.DoesNotExist:
                cart_item = CartItem.objects.create(
                    cart=cart,
                    offer=offer,
                    quantity=item.quantity
                )
            
            return AddToCart(cart=cart)
        except Offer.DoesNotExist:
            raise GraphQLError(f"Offer with ID {item.offer_id} not found")
        except Exception as e:
            raise GraphQLError(str(e))

class UpdateCartItem(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        quantity = graphene.Int(required=True)
    
    cart_item = graphene.Field(CartItemType)
    
    @staticmethod
    def mutate(root, info, id, quantity):
        try:
            cart_item = CartItem.objects.get(pk=id)
            
            if quantity <= 0:
                cart_item.delete()
                return None
            
            cart_item.quantity = quantity
            cart_item.save()
            
            return UpdateCartItem(cart_item=cart_item)
        except CartItem.DoesNotExist:
            raise GraphQLError(f"Cart item with ID {id} not found")
        except Exception as e:
            raise GraphQLError(str(e))

class RemoveFromCart(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
    
    success = graphene.Boolean()
    
    @staticmethod
    def mutate(root, info, id):
        try:
            cart_item = CartItem.objects.get(pk=id)
            cart_item.delete()
            return RemoveFromCart(success=True)
        except CartItem.DoesNotExist:
            return RemoveFromCart(success=False)

class ClearCart(graphene.Mutation):
    class Arguments:
        cart_id = graphene.ID()
        session_id = graphene.String()
    
    success = graphene.Boolean()
    
    @staticmethod
    def mutate(root, info, cart_id=None, session_id=None):
        try:
            cart = None
            
            if cart_id:
                cart = Cart.objects.get(pk=cart_id)
            elif session_id:
                cart = Cart.objects.get(session_id=session_id)
            else:
                return ClearCart(success=False)
            
            CartItem.objects.filter(cart=cart).delete()
            return ClearCart(success=True)
        except Cart.DoesNotExist:
            return ClearCart(success=False)
        except Exception as e:
            raise GraphQLError(str(e))

class CartMutation(graphene.ObjectType):
    add_to_cart = AddToCart.Field()
    update_cart_item = UpdateCartItem.Field()
    remove_from_cart = RemoveFromCart.Field()
    clear_cart = ClearCart.Field() 