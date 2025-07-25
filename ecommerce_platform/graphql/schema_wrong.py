import graphene
from .queries import ProductQuery, OfferQuery, AffiliateQuery, CartQuery
from .mutations import ProductMutation, AffiliateMutation, CartMutation

class Query(ProductQuery, OfferQuery, AffiliateQuery, CartQuery, graphene.ObjectType):
    """Root query type that combines all query types."""
    pass

class Mutation(ProductMutation, AffiliateMutation, CartMutation, graphene.ObjectType):
    """Root mutation type that combines all mutation types."""
    pass

schema = graphene.Schema(
    query=Query, 
    mutation=Mutation
) 