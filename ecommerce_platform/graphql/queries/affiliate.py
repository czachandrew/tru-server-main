import graphene
from affiliates.models import AffiliateLink
from ..types import AffiliateLinkType
import logging
import redis
import json
from django.conf import settings
from graphql import GraphQLError

def get_redis_kwargs():
    """Helper function to get Redis connection parameters"""
    redis_kwargs = {
        'host': getattr(settings, 'REDIS_HOST', 'localhost'),
        'port': getattr(settings, 'REDIS_PORT', 6379),
        'decode_responses': True
    }
    if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
        redis_kwargs['password'] = settings.REDIS_PASSWORD
    return redis_kwargs

# Types for user affiliate activity
class RecentClickType(graphene.ObjectType):
    id = graphene.ID()
    affiliate_link = graphene.Field(AffiliateLinkType)
    clicked_at = graphene.DateTime()
    target_domain = graphene.String()
    session_duration = graphene.Int()
    has_purchase_intent = graphene.Boolean()

class ProjectedEarningType(graphene.ObjectType):
    id = graphene.ID()
    amount = graphene.Float()
    created_at = graphene.DateTime()
    confidence_level = graphene.String()
    intent_stage = graphene.String()
    platform = graphene.String()

class WalletSummaryType(graphene.ObjectType):
    available_balance = graphene.Float()
    pending_balance = graphene.Float()
    total_balance = graphene.Float()

class UserAffiliateActivityType(graphene.ObjectType):
    recent_clicks = graphene.List(RecentClickType)
    projected_earnings = graphene.List(ProjectedEarningType)
    wallet_summary = graphene.Field(WalletSummaryType)

class AffiliateQuery(graphene.ObjectType):
    affiliate_links = graphene.List(AffiliateLinkType, product_id=graphene.ID(required=True))
    check_affiliate_task = graphene.JSONString(task_id=graphene.String(required=True))
    user_affiliate_activity = graphene.Field(UserAffiliateActivityType)
    
    def resolve_affiliate_links(self, info, product_id):
        return AffiliateLink.objects.filter(product_id=product_id)

    def resolve_check_affiliate_task(self, info, task_id):
        """Check status of an affiliate link generation task"""
        logger = logging.getLogger('affiliate_tasks')
        logger.info(f"Checking affiliate task status for: {task_id}")
        
        redis_kwargs = get_redis_kwargs()
        r = redis.Redis(**redis_kwargs)
        
        # Check if task is still pending
        asin = r.get(f"pending_standalone_task:{task_id}")
        if asin:
            return {
                "status": "processing",
                "message": "Task is still being processed"
            }
        
        # Check if results are available
        result_json = r.get(f"standalone_task_status:{task_id}")
        if result_json:
            return json.loads(result_json)
        
        return {
            "status": "not_found",
            "message": "Task not found or expired"
        }
    
    def resolve_user_affiliate_activity(self, info):
        """Get user's recent affiliate activity and projected earnings"""
        from affiliates.models import AffiliateClickEvent
        from users.models import WalletTransaction
        
        # Check authentication
        if not info.context.user.is_authenticated:
            raise GraphQLError("Authentication required")
        
        try:
            user = info.context.user
            
            # Get recent clicks
            recent_clicks = AffiliateClickEvent.objects.filter(
                user=user,
                is_active=True
            ).order_by('-clicked_at')[:10]
            
            # Get pending projected earnings
            pending_transactions = WalletTransaction.objects.filter(
                user=user,
                transaction_type='EARNING_PROJECTED',
                status='PENDING'
            ).order_by('-created_at')
            
            # Format recent clicks
            recent_clicks_data = []
            for click in recent_clicks:
                recent_clicks_data.append(RecentClickType(
                    id=click.id,
                    affiliate_link=click.affiliate_link,
                    clicked_at=click.clicked_at,
                    target_domain=click.target_domain,
                    session_duration=click.session_duration,
                    has_purchase_intent=click.purchase_intents.exists()
                ))
            
            # Format projected earnings
            projected_earnings_data = []
            for txn in pending_transactions:
                projected_earnings_data.append(ProjectedEarningType(
                    id=txn.id,
                    amount=float(txn.amount),
                    created_at=txn.created_at,
                    confidence_level=txn.metadata.get('confidence_level'),
                    intent_stage=txn.metadata.get('intent_stage'),
                    platform=txn.affiliate_link.platform if txn.affiliate_link else None
                ))
            
            # Format wallet summary
            wallet_summary = WalletSummaryType(
                available_balance=float(user.profile.available_balance),
                pending_balance=float(user.profile.pending_balance),
                total_balance=float(user.profile.total_balance)
            )
            
            return UserAffiliateActivityType(
                recent_clicks=recent_clicks_data,
                projected_earnings=projected_earnings_data,
                wallet_summary=wallet_summary
            )
            
        except Exception as e:
            logger = logging.getLogger('affiliate_tasks')
            logger.error(f"Error getting user affiliate activity: {str(e)}")
            raise GraphQLError("Failed to get affiliate activity") 