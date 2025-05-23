from graphene_django import DjangoObjectType
from affiliates.models import AffiliateLink


class AffiliateLinkType(DjangoObjectType):
    class Meta:
        model = AffiliateLink
        fields = "__all__"
