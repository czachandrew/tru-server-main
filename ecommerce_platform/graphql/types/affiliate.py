from graphene_django import DjangoObjectType
from affiliates.models import AffiliateLink

class AffiliateLinkType(DjangoObjectType):
    class Meta:
        model = AffiliateLink
        fields = (
            "id", "product", "platform", "platform_id", "original_url",
            "affiliate_url", "clicks", "conversions", "revenue",
            "is_active", "created_at", "updated_at"
        ) 