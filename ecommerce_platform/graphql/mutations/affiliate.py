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
import traceback

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

# Extension tracking mutations
class TrackAffiliateClickInput(graphene.InputObjectType):
    affiliate_link_id = graphene.ID(required=True)
    session_id = graphene.String(required=True)
    target_domain = graphene.String(required=True)
    referrer_url = graphene.String()
    source = graphene.String()
    product_data = graphene.JSONString()
    browser_fingerprint = graphene.String()

class TrackAffiliateClick(graphene.Mutation):
    class Arguments:
        input = TrackAffiliateClickInput(required=True)
    
    success = graphene.Boolean()
    click_event_id = graphene.ID()
    message = graphene.String()
    
    @staticmethod
    def mutate(root, info, input):
        from affiliates.models import AffiliateClickEvent
        
        # Check authentication
        if not info.context.user.is_authenticated:
            raise GraphQLError("Authentication required")
        
        try:
            # Get affiliate link - try by platform_id first (ASIN), then by linkId if needed
            affiliate_link = None
            
            # Parse product data once
            product_data = {}
            if input.product_data:
                if isinstance(input.product_data, str):
                    product_data = json.loads(input.product_data)
                else:
                    product_data = input.product_data
            
            # Extract ASIN from the extension's product data or affiliate_link_id
            try:
                import json
                from urllib.parse import urlparse, parse_qs
                
                # Try to get ASIN from product data
                asin = product_data.get('asin') or product_data.get('sku')
                if asin:
                    affiliate_link = AffiliateLink.objects.get(
                        platform_id=asin,
                        platform='amazon',
                        is_active=True
                    )
                
                # If not found and we have a URL in referrer or somewhere, extract ASIN from URL
                if not affiliate_link:
                    # The affiliate_link_id might be the linkId, but we need to find by ASIN
                    # For now, check if the affiliate_link_id looks like an ASIN (starts with B)
                    if input.affiliate_link_id.startswith('B') and len(input.affiliate_link_id) == 10:
                        # This looks like an ASIN
                        affiliate_link = AffiliateLink.objects.get(
                            platform_id=input.affiliate_link_id,
                            platform='amazon',
                            is_active=True
                        )
                    else:
                        # Try to find by database ID as fallback
                        try:
                            affiliate_link = AffiliateLink.objects.get(
                                id=int(input.affiliate_link_id),
                                is_active=True
                            )
                        except (ValueError, AffiliateLink.DoesNotExist):
                            pass
                            
            except (json.JSONDecodeError, AffiliateLink.DoesNotExist):
                pass
            
            if not affiliate_link:
                raise AffiliateLink.DoesNotExist()
            
            # Create click event
            click_event = AffiliateClickEvent.objects.create(
                user=info.context.user,
                affiliate_link=affiliate_link,
                source=input.source or 'extension',
                session_id=input.session_id,
                referrer_url=input.referrer_url or '',
                target_domain=input.target_domain,
                product_data=product_data if input.product_data else {},
                user_agent=info.context.META.get('HTTP_USER_AGENT', ''),
                browser_fingerprint=input.browser_fingerprint or '',
            )
            
            # Update affiliate link click count
            affiliate_link.record_click()
            
            logger = logging.getLogger('affiliate_tasks')
            logger.info(f"Tracked affiliate click: {click_event.id} for user {info.context.user.email}")
            
            return TrackAffiliateClick(
                success=True,
                click_event_id=click_event.id,
                message="Click tracked successfully"
            )
            
        except AffiliateLink.DoesNotExist:
            raise GraphQLError("Affiliate link not found or inactive")
        except Exception as e:
            logger = logging.getLogger('affiliate_tasks')
            logger.error(f"Error tracking affiliate click: {str(e)}")
            raise GraphQLError("Failed to track click")

class TrackPurchaseIntentInput(graphene.InputObjectType):
    click_event_id = graphene.ID(required=True)
    intent_stage = graphene.String(required=True)
    confidence_level = graphene.String(required=True)
    page_url = graphene.String(required=True)
    page_title = graphene.String()
    cart_total = graphene.Float()
    cart_items = graphene.JSONString()
    matched_products = graphene.JSONString()

class ProjectedEarningType(graphene.ObjectType):
    # Core fields for trackPurchaseIntent mutation
    transaction_id = graphene.ID()
    amount = graphene.Float()
    confidence_level = graphene.String()
    user_balance = graphene.Float()
    
    # Additional fields for userAffiliateActivity query
    id = graphene.ID()
    created_at = graphene.DateTime()
    intent_stage = graphene.String()
    platform = graphene.String()
    
    # CamelCase aliases for frontend compatibility
    transactionId = graphene.ID()
    confidenceLevel = graphene.String()
    userBalance = graphene.Float()
    createdAt = graphene.DateTime()
    intentStage = graphene.String()
    
    def resolve_transactionId(self, info):
        return self.transaction_id or self.id
    
    def resolve_confidenceLevel(self, info):
        return self.confidence_level
    
    def resolve_userBalance(self, info):
        return self.user_balance
    
    def resolve_createdAt(self, info):
        return self.created_at
    
    def resolve_intentStage(self, info):
        return self.intent_stage
    
    def resolve_id(self, info):
        return self.transaction_id or getattr(self, 'id', None)

class TrackPurchaseIntent(graphene.Mutation):
    class Arguments:
        input = TrackPurchaseIntentInput(required=True)
    
    success = graphene.Boolean()
    intent_event_id = graphene.ID()
    created = graphene.Boolean()
    message = graphene.String()
    projected_earning = graphene.Field(ProjectedEarningType)
    
    @staticmethod
    def mutate(root, info, input):
        from affiliates.models import AffiliateClickEvent, PurchaseIntentEvent
        from decimal import Decimal
        
        # Check authentication
        if not info.context.user.is_authenticated:
            raise GraphQLError("Authentication required")
        
        try:
            # Get click event - try by session_id first (for extension), then by database id
            click_event = None
            try:
                # First try to find by session_id (extension sends session IDs like "affiliate_arrival_1753202207873")
                click_event = AffiliateClickEvent.objects.get(
                    session_id=input.click_event_id,
                    user=info.context.user,
                    is_active=True
                )
            except AffiliateClickEvent.DoesNotExist:
                # Fallback to database ID lookup for backward compatibility
                try:
                    click_event = AffiliateClickEvent.objects.get(
                        id=int(input.click_event_id),
                        user=info.context.user,
                        is_active=True
                    )
                except (ValueError, AffiliateClickEvent.DoesNotExist):
                    pass
            
            if not click_event:
                raise AffiliateClickEvent.DoesNotExist()
            
            # Validate confidence level
            valid_confidence_levels = ['LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH']
            if input.confidence_level not in valid_confidence_levels:
                raise GraphQLError(f"Invalid confidence level. Must be one of: {valid_confidence_levels}")
            
            # Calculate confidence score based on level
            confidence_score_map = {
                'LOW': 0.4,
                'MEDIUM': 0.6,
                'HIGH': 0.8,
                'VERY_HIGH': 0.95
            }
            confidence_score = confidence_score_map[input.confidence_level]
            
            # Handle both string and already-parsed list cases for JSON fields
            def safe_json_parse(data):
                if data is None:
                    return []
                if isinstance(data, (list, dict)):
                    return data  # Already parsed by GraphQL
                if isinstance(data, str):
                    try:
                        return json.loads(data)
                    except json.JSONDecodeError:
                        return []
                return []
            
            cart_items_parsed = safe_json_parse(input.cart_items)
            matched_products_parsed = safe_json_parse(input.matched_products)
            
            # Create or update purchase intent event
            intent_event, created = PurchaseIntentEvent.objects.get_or_create(
                click_event=click_event,
                intent_stage=input.intent_stage,
                defaults={
                    'confidence_level': input.confidence_level,
                    'confidence_score': confidence_score,
                    'cart_total': Decimal(str(input.cart_total)) if input.cart_total else None,
                    'cart_items': cart_items_parsed,
                    'matched_products': matched_products_parsed,
                    'page_url': input.page_url,
                    'page_title': input.page_title or '',
                }
            )
            
            # If not created, update existing event
            if not created:
                intent_event.confidence_level = input.confidence_level
                intent_event.confidence_score = confidence_score
                intent_event.cart_total = Decimal(str(input.cart_total)) if input.cart_total else None
                intent_event.cart_items = cart_items_parsed
                intent_event.matched_products = matched_products_parsed
                intent_event.page_url = input.page_url
                intent_event.page_title = input.page_title or ''
                intent_event.save()
            
            # Create projected earning if criteria met
            projected_transaction = None
            projected_earning = None
            
            if intent_event.should_create_projection():
                projected_transaction = intent_event.create_projected_earning()
                
                if projected_transaction:
                    projected_earning = ProjectedEarningType(
                        transaction_id=projected_transaction.id,
                        amount=float(projected_transaction.amount),
                        confidence_level=input.confidence_level,
                        user_balance=float(info.context.user.profile.pending_balance)
                    )
            
            logger = logging.getLogger('affiliate_tasks')
            logger.info(f"Tracked purchase intent: {intent_event.id} for user {info.context.user.email}")
            
            return TrackPurchaseIntent(
                success=True,
                intent_event_id=intent_event.id,
                created=created,
                message="Purchase intent tracked successfully",
                projected_earning=projected_earning
            )
            
        except AffiliateClickEvent.DoesNotExist:
            raise GraphQLError("Click event not found or inactive")
        except Exception as e:
            logger = logging.getLogger('affiliate_tasks')
            logger.error(f"Error tracking purchase intent: {str(e)}")
            raise GraphQLError("Failed to track purchase intent")

class UpdateSessionDurationInput(graphene.InputObjectType):
    click_event_id = graphene.ID(required=True)
    duration_seconds = graphene.Int(required=True)

class UpdateSessionDuration(graphene.Mutation):
    class Arguments:
        input = UpdateSessionDurationInput(required=True)
    
    success = graphene.Boolean()
    message = graphene.String()
    
    @staticmethod
    def mutate(root, info, input):
        from affiliates.models import AffiliateClickEvent
        
        # Check authentication
        if not info.context.user.is_authenticated:
            raise GraphQLError("Authentication required")
        
        try:
            # Get click event - try by session_id first (for extension), then by database id
            click_event = None
            try:
                # First try to find by session_id (extension sends session IDs like "affiliate_arrival_1753202207873")
                click_event = AffiliateClickEvent.objects.get(
                    session_id=input.click_event_id,
                    user=info.context.user,
                    is_active=True
                )
            except AffiliateClickEvent.DoesNotExist:
                # Fallback to database ID lookup for backward compatibility
                try:
                    click_event = AffiliateClickEvent.objects.get(
                        id=int(input.click_event_id),
                        user=info.context.user,
                        is_active=True
                    )
                except (ValueError, AffiliateClickEvent.DoesNotExist):
                    pass
            
            if not click_event:
                raise AffiliateClickEvent.DoesNotExist()
            
            # Update session duration
            click_event.update_session_duration(input.duration_seconds)
            
            return UpdateSessionDuration(
                success=True,
                message="Session duration updated successfully"
            )
            
        except AffiliateClickEvent.DoesNotExist:
            raise GraphQLError("Click event not found or inactive")
        except Exception as e:
            logger = logging.getLogger('affiliate_tasks')
            logger.error(f"Error updating session duration: {str(e)}")
            raise GraphQLError("Failed to update session duration")

# Update the mutation class to include the new extension mutations
class ExtendedAffiliateMutation(graphene.ObjectType):
    create_affiliate_link = CreateAffiliateLink.Field()
    create_amazon_affiliate_link = CreateAmazonAffiliateLink.Field()
    update_affiliate_link = UpdateAffiliateLink.Field()
    
    # Extension tracking mutations
    track_affiliate_click = TrackAffiliateClick.Field()
    track_purchase_intent = TrackPurchaseIntent.Field()
    update_session_duration = UpdateSessionDuration.Field()

# Keep the old class for backward compatibility
AffiliateMutation = ExtendedAffiliateMutation 