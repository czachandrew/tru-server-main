import graphene
from affiliates.models import AffiliateLink
from ..types import AffiliateLinkType

class AffiliateQuery(graphene.ObjectType):
    affiliate_links = graphene.List(AffiliateLinkType, product_id=graphene.ID(required=True))
    
    def resolve_affiliate_links(self, info, product_id):
        return AffiliateLink.objects.filter(product_id=product_id) 