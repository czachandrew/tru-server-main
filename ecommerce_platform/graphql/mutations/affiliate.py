import graphene
from graphql import GraphQLError
from products.models import Product
from affiliates.models import AffiliateLink
from ..types import AffiliateLinkType

class AffiliateLinkInput(graphene.InputObjectType):
    product_id = graphene.ID(required=True)
    platform = graphene.String(required=True)
    platform_id = graphene.String(required=True)
    original_url = graphene.String(required=True)

class CreateAffiliateLink(graphene.Mutation):
    class Arguments:
        input = AffiliateLinkInput(required=True)
    
    affiliate_link = graphene.Field(AffiliateLinkType)
    
    @staticmethod
    def mutate(root, info, input):
        try:
            product = Product.objects.get(pk=input.product_id)
            
            affiliate_link = AffiliateLink(
                product=product,
                platform=input.platform,
                platform_id=input.platform_id,
                original_url=input.original_url,
                affiliate_url='',  # Will be populated later
                is_active=True
            )
            affiliate_link.save()
            
            return CreateAffiliateLink(affiliate_link=affiliate_link)
        except Product.DoesNotExist:
            raise GraphQLError(f"Product with ID {input.product_id} not found")
        except Exception as e:
            raise GraphQLError(str(e))

class CreateAmazonAffiliateLink(graphene.Mutation):
    class Arguments:
        asin = graphene.String(required=True)
        product_id = graphene.ID()
    
    affiliate_link = graphene.Field(AffiliateLinkType)
    
    @staticmethod
    def mutate(root, info, asin, product_id=None):
        try:
            # If product_id is not provided, check if product exists with this ASIN
            if not product_id:
                try:
                    existing_link = AffiliateLink.objects.get(
                        platform='amazon',
                        platform_id=asin
                    )
                    return CreateAmazonAffiliateLink(affiliate_link=existing_link)
                except AffiliateLink.DoesNotExist:
                    raise GraphQLError("No product found for this ASIN. Please create product first.")
            
            product = Product.objects.get(pk=product_id)
            
            # Create basic affiliate link
            affiliate_link = AffiliateLink(
                product=product,
                platform='amazon',
                platform_id=asin,
                original_url=f"https://www.amazon.com/dp/{asin}",
                affiliate_url='',  # Will be populated by background task
                is_active=True
            )
            affiliate_link.save()
            
            # Queue background task to generate actual affiliate URL
            from django_q.tasks import async_task
            async_task('affiliates.tasks.generate_amazon_affiliate_url', 
                      affiliate_link.id, asin)
            
            return CreateAmazonAffiliateLink(affiliate_link=affiliate_link)
        except Product.DoesNotExist:
            raise GraphQLError(f"Product with ID {product_id} not found")
        except Exception as e:
            raise GraphQLError(str(e))

class UpdateAffiliateLink(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        is_active = graphene.Boolean()
    
    affiliate_link = graphene.Field(AffiliateLinkType)
    
    @staticmethod
    def mutate(root, info, id, is_active=None):
        try:
            affiliate_link = AffiliateLink.objects.get(pk=id)
            
            if is_active is not None:
                affiliate_link.is_active = is_active
                
            affiliate_link.save()
            
            return UpdateAffiliateLink(affiliate_link=affiliate_link)
        except AffiliateLink.DoesNotExist:
            raise GraphQLError(f"Affiliate link with ID {id} not found")
        except Exception as e:
            raise GraphQLError(str(e))

class AffiliateMutation(graphene.ObjectType):
    create_affiliate_link = CreateAffiliateLink.Field()
    create_amazon_affiliate_link = CreateAmazonAffiliateLink.Field()
    update_affiliate_link = UpdateAffiliateLink.Field() 