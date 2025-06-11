import graphene
from graphql import GraphQLError
from products.models import Product
from affiliates.models import AffiliateLink
from ..types import AffiliateLinkType
import logging
from django_q.tasks import async_task
import json
import redis
from django.conf import settings

class AffiliateLinkInput(graphene.InputObjectType):
    product_id = graphene.ID(required=True)
    platform = graphene.String(required=True)
    platform_id = graphene.String(required=True)
    original_url = graphene.String(required=True)

class ProductInput(graphene.InputObjectType):
    """Input type for product data"""
    name = graphene.String()
    partNumber = graphene.String()
    manufacturer = graphene.String()
    description = graphene.String()
    mainImage = graphene.String()
    price = graphene.Float()
    sourceUrl = graphene.String()
    technicalDetails = graphene.JSONString()

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
        productId = graphene.String(required=True)
        currentUrl = graphene.String(required=False)
        productData = ProductInput(required=False)
    
    # Return fields that match the Chrome extension's expectations
    taskId = graphene.String()
    affiliateUrl = graphene.String()
    status = graphene.String()
    message = graphene.String()
    
    @staticmethod
    def mutate(root, info, asin, productId=None, currentUrl=None, productData=None):
        try:
            logger = logging.getLogger('affiliate_tasks')
            logger.info(f"CreateAmazonAffiliateLink called with: asin={asin}, productId={productId}, currentUrl={currentUrl}")
            
            if productData:
                logger.info(f"Product data: name={productData.name}, manufacturer={productData.manufacturer}")
            
            # Special handling for 'new_product' product_id from Chrome extension
            if productId == 'new_product' and productData:
                logger.info("New product creation requested")
                
                # Queue task to generate affiliate URL and create product
                logger.info(f"Queueing task to generate affiliate URL for ASIN: {asin}")
                task_id = async_task(
                    'affiliates.tasks.generate_standalone_amazon_affiliate_url', 
                    asin, 
                    productData.sourceUrl or f"https://www.amazon.com/dp/{asin}"
                )
                logger.info(f"Queued task ID: {task_id}")
                
                # Store product data in Redis
                redis_kwargs = get_redis_kwargs()
                r = redis.Redis(**redis_kwargs)
                
                # Store all product data with the task_id
                product_data_dict = {
                    "asin": asin,
                    "name": productData.name,
                    "description": productData.description,
                    "mainImage": productData.mainImage,
                    "manufacturer": productData.manufacturer,
                    "partNumber": productData.partNumber or asin,
                    "price": productData.price,
                    "sourceUrl": productData.sourceUrl,
                    "technicalDetails": productData.technicalDetails
                }
                r.set(f"pending_product_data:{task_id}", json.dumps(product_data_dict), ex=86400)
                
                return CreateAmazonAffiliateLink(
                    taskId=task_id,
                    affiliateUrl="pending",
                    status="processing",
                    message="Affiliate link is being generated"
                )
            elif productId == 'temporary':
                # Handle the old case for backward compatibility
                logger.info("Temporary product ID detected - returning placeholder")
                
                task_id = async_task(
                    'affiliates.tasks.generate_standalone_amazon_affiliate_url', 
                    asin, 
                    currentUrl or f"https://www.amazon.com/dp/{asin}"
                )
                logger.info(f"Queued task ID: {task_id}")
                
                return CreateAmazonAffiliateLink(
                    taskId=task_id,
                    affiliateUrl="pending",
                    status="processing",
                    message="Affiliate link is being generated"
                )
            else:
                return CreateAmazonAffiliateLink(
                    taskId=None,
                    affiliateUrl=None,
                    status="error",
                    message="Invalid productId specified"
                )
                
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Error in CreateAmazonAffiliateLink: {str(e)}\n{tb}")
            return CreateAmazonAffiliateLink(
                taskId=None,
                affiliateUrl=None,
                status="error",
                message=str(e)
            )

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