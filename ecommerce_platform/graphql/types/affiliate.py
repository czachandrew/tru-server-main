from graphene_django import DjangoObjectType
from affiliates.models import AffiliateLink, ProductAssociation
import graphene


class AffiliateLinkType(DjangoObjectType):
    class Meta:
        model = AffiliateLink
        fields = "__all__"

class ProductAssociationType(DjangoObjectType):
    click_through_rate = graphene.Float()
    conversion_rate = graphene.Float()
    
    class Meta:
        model = ProductAssociation
        fields = "__all__"
    
    def resolve_click_through_rate(self, info):
        return self.click_through_rate
    
    def resolve_conversion_rate(self, info):
        return self.conversion_rate
