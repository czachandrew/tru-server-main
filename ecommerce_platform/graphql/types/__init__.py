import graphene
# Make sure to import all your types here
from .user import UserType, UserProfileType
# Import your ProductType - adjust the path as needed
from .product import ProductType, CategoryType, ManufacturerType
# Import any other types you need
from .scalar import JSONScalar
from .offer import OfferType, VendorType
from .affiliate import AffiliateLinkType
from .cart import CartType, CartItemType


# Create the response objects first
class ProductExistsResponse(graphene.ObjectType):
    exists = graphene.Boolean()
    product = graphene.Field('ecommerce_platform.graphql.types.product.Product')
    message = graphene.String()

# Use lazy imports or functions
def get_product_types():
    from .product import Product, Category, Manufacturer
    return Product, Category, Manufacturer

def get_offer_types():
    from .offer import Offer, Vendor
    return Offer, Vendor

def get_affiliate_types():
    from .affiliate import AffiliateLinkType
    return AffiliateLinkType

def get_cart_types():
    from .cart import CartType, CartItemType, UserType
    return CartType, CartItemType, UserType

