import graphene
from offers.models import Offer
from vendors.models import Vendor
from ..types.offer import Offer, Vendor

class OfferQuery(graphene.ObjectType):
    offers_by_product = graphene.List(Offer, product_id=graphene.ID(required=True))
    vendors = graphene.List(Vendor)
    
    def resolve_offers_by_product(self, info, product_id):
        return Offer.objects.filter(product_id=product_id)
    
    def resolve_vendors(self, info):
        return Vendor.objects.filter(is_active=True) 