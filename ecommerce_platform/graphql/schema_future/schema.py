import graphene
from ..queries import ProductQuery, OfferQuery, AffiliateQuery, CartQuery, UserQuery
from ..mutations import ProductMutation, AffiliateMutation, CartMutation, AuthMutation
from ..types import ProductType, CategoryType, ManufacturerType

class Query(ProductQuery, OfferQuery, AffiliateQuery, CartQuery, UserQuery, graphene.ObjectType):
    pass

class Mutation(AuthMutation, ProductMutation, AffiliateMutation, CartMutation, graphene.ObjectType):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation) 