"""
Activity Metrics Service - Track user engagement for dynamic revenue sharing
"""

from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Count, Sum, Q
from django.utils import timezone
from typing import Dict, Any, Optional
import logging

from .models import User, UserProfile, WalletTransaction
from affiliates.models import AffiliateLink
from products.models import Product

logger = logging.getLogger(__name__)


class ActivityMetricsService:
    """Service for tracking and calculating user activity metrics"""
    
    # Activity scoring weights
    WEIGHTS = {
        'affiliate_clicks': Decimal('0.10'),      # Each click = 0.10 points
        'successful_conversions': Decimal('0.50'), # Each conversion = 0.50 points
        'days_active': Decimal('0.05'),           # Each active day = 0.05 points
        'search_queries': Decimal('0.02'),        # Each search = 0.02 points
        'referrals_made': Decimal('1.00'),        # Each referral = 1.00 points
        'consecutive_days': Decimal('0.20'),      # Streak bonus = 0.20 points
        'high_value_conversions': Decimal('0.30'), # High-value conversion bonus
    }
    
    @staticmethod
    def calculate_user_activity_score(user: User, days_back: int = 30) -> Dict[str, Any]:
        """
        Calculate comprehensive activity score for a user
        
        Args:
            user: The user to calculate score for
            days_back: Number of days to look back for activity
            
        Returns:
            Dict containing activity metrics and calculated score
        """
        cutoff_date = timezone.now() - timedelta(days=days_back)
        
        # Get affiliate link clicks (from click tracking)
        affiliate_clicks = AffiliateLink.objects.filter(
            wallet_transactions__user=user,
            wallet_transactions__created_at__gte=cutoff_date
        ).aggregate(total_clicks=Sum('clicks'))['total_clicks'] or 0
        
        # Get successful conversions
        successful_conversions = WalletTransaction.objects.filter(
            user=user,
            transaction_type='EARNING_CONFIRMED',
            created_at__gte=cutoff_date
        ).count()
        
        # Get days active (days with any wallet transaction)
        days_active = WalletTransaction.objects.filter(
            user=user,
            created_at__gte=cutoff_date
        ).values('created_at__date').distinct().count()
        
        # Get search queries (would need to implement search tracking)
        # For now, we'll estimate based on affiliate interactions
        search_queries = affiliate_clicks * 2  # Estimate 2 searches per affiliate click
        
        # Get referrals made (would need referral system)
        referrals_made = 0  # Placeholder for future referral system
        
        # Calculate consecutive days streak
        consecutive_days = ActivityMetricsService._calculate_consecutive_days(user, cutoff_date)
        
        # Calculate high-value conversions (above average)
        avg_conversion_value = WalletTransaction.objects.filter(
            user=user,
            transaction_type='EARNING_CONFIRMED'
        ).aggregate(avg_amount=Sum('amount'))['avg_amount'] or Decimal('0.00')
        
        high_value_conversions = WalletTransaction.objects.filter(
            user=user,
            transaction_type='EARNING_CONFIRMED',
            amount__gt=avg_conversion_value,
            created_at__gte=cutoff_date
        ).count()
        
        # Calculate raw score
        raw_score = (
            Decimal(str(affiliate_clicks)) * ActivityMetricsService.WEIGHTS['affiliate_clicks'] +
            Decimal(str(successful_conversions)) * ActivityMetricsService.WEIGHTS['successful_conversions'] +
            Decimal(str(days_active)) * ActivityMetricsService.WEIGHTS['days_active'] +
            Decimal(str(search_queries)) * ActivityMetricsService.WEIGHTS['search_queries'] +
            Decimal(str(referrals_made)) * ActivityMetricsService.WEIGHTS['referrals_made'] +
            Decimal(str(consecutive_days)) * ActivityMetricsService.WEIGHTS['consecutive_days'] +
            Decimal(str(high_value_conversions)) * ActivityMetricsService.WEIGHTS['high_value_conversions']
        )
        
        # Normalize score to 1.00-5.00 range
        normalized_score = ActivityMetricsService._normalize_score(raw_score)
        
        metrics = {
            'raw_score': raw_score,
            'normalized_score': normalized_score,
            'metrics': {
                'affiliate_clicks': affiliate_clicks,
                'successful_conversions': successful_conversions,
                'days_active': days_active,
                'search_queries': search_queries,
                'referrals_made': referrals_made,
                'consecutive_days': consecutive_days,
                'high_value_conversions': high_value_conversions,
            },
            'revenue_share_rate': ActivityMetricsService._calculate_revenue_share_rate(normalized_score),
            'period_days': days_back,
            'calculated_at': timezone.now()
        }
        
        logger.info(f"Activity score calculated for {user.email}: {normalized_score} (raw: {raw_score})")
        return metrics
    
    @staticmethod
    def _calculate_consecutive_days(user: User, cutoff_date: datetime) -> int:
        """Calculate the longest consecutive days streak"""
        # Get all dates with activity
        activity_dates = WalletTransaction.objects.filter(
            user=user,
            created_at__gte=cutoff_date
        ).values_list('created_at__date', flat=True).distinct().order_by('created_at__date')
        
        if not activity_dates:
            return 0
        
        # Calculate longest streak
        max_streak = 1
        current_streak = 1
        
        for i in range(1, len(activity_dates)):
            if activity_dates[i] == activity_dates[i-1] + timedelta(days=1):
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 1
        
        return max_streak
    
    @staticmethod
    def _normalize_score(raw_score: Decimal) -> Decimal:
        """Normalize raw score to 1.00-5.00 range"""
        # Define score ranges (these can be adjusted based on data)
        min_score = Decimal('1.00')
        max_score = Decimal('5.00')
        
        # Score thresholds (can be tuned)
        thresholds = {
            Decimal('0.00'): Decimal('1.00'),   # Minimal activity
            Decimal('5.00'): Decimal('2.00'),   # Low activity
            Decimal('15.00'): Decimal('3.00'),  # Moderate activity
            Decimal('30.00'): Decimal('4.00'),  # High activity
            Decimal('50.00'): Decimal('5.00'),  # Very high activity
        }
        
        # Find appropriate score
        for threshold, score in sorted(thresholds.items()):
            if raw_score <= threshold:
                return score
        
        return max_score
    
    @staticmethod
    def _calculate_revenue_share_rate(activity_score: Decimal) -> Decimal:
        """Calculate revenue share rate based on activity score"""
        base_rate = Decimal('0.15')  # 15% base rate
        max_bonus = Decimal('0.05')  # Up to 5% bonus
        max_score = Decimal('5.00')
        min_score = Decimal('1.00')
        
        # Linear interpolation between 15% and 20%
        score_factor = (activity_score - min_score) / (max_score - min_score)
        bonus = max_bonus * score_factor
        
        return base_rate + bonus
    
    @staticmethod
    def update_user_activity_score(user: User, force_update: bool = False) -> Dict[str, Any]:
        """
        Update user's activity score in their profile
        
        Args:
            user: The user to update
            force_update: Force update even if recently updated
            
        Returns:
            Dict with update results
        """
        profile = user.profile
        
        # Check if we need to update (don't update too frequently)
        if not force_update and profile.updated_at > timezone.now() - timedelta(hours=6):
            return {
                'updated': False,
                'reason': 'Recently updated',
                'current_score': profile.activity_score,
                'current_rate': profile.revenue_share_rate
            }
        
        # Calculate new activity score
        metrics = ActivityMetricsService.calculate_user_activity_score(user)
        new_score = metrics['normalized_score']
        
        # Update profile if score changed significantly
        score_change = abs(new_score - profile.activity_score)
        if score_change >= Decimal('0.10') or force_update:
            old_score = profile.activity_score
            old_rate = profile.revenue_share_rate
            
            profile.activity_score = new_score
            profile.save()
            
            # Log the change
            logger.info(f"Updated activity score for {user.email}: {old_score} -> {new_score}")
            
            # Create activity bonus transaction if score increased significantly
            if new_score > old_score + Decimal('0.25'):
                ActivityMetricsService._create_activity_bonus(user, old_score, new_score)
            
            return {
                'updated': True,
                'old_score': old_score,
                'new_score': new_score,
                'old_rate': old_rate,
                'new_rate': profile.revenue_share_rate,
                'metrics': metrics
            }
        
        return {
            'updated': False,
            'reason': 'No significant change',
            'current_score': profile.activity_score,
            'current_rate': profile.revenue_share_rate
        }
    
    @staticmethod
    def _create_activity_bonus(user: User, old_score: Decimal, new_score: Decimal) -> None:
        """Create a small bonus transaction for activity score increase"""
        try:
            # Small bonus for activity improvement
            bonus_amount = Decimal('0.50')  # $0.50 bonus
            
            profile = user.profile
            
            WalletTransaction.objects.create(
                user=user,
                transaction_type='BONUS_ACTIVITY',
                amount=bonus_amount,
                balance_before=profile.available_balance,
                balance_after=profile.available_balance + bonus_amount,
                description=f"Activity bonus for score improvement: {old_score} -> {new_score}",
                status='CONFIRMED',
                processed_at=timezone.now(),
                metadata={
                    'old_score': str(old_score),
                    'new_score': str(new_score),
                    'bonus_type': 'activity_improvement'
                }
            )
            
            # Update profile balance
            profile.available_balance += bonus_amount
            profile.save()
            
            logger.info(f"Created activity bonus for {user.email}: ${bonus_amount}")
            
        except Exception as e:
            logger.error(f"Failed to create activity bonus for {user.email}: {e}")
    
    @staticmethod
    def get_activity_leaderboard(limit: int = 10) -> list:
        """
        Get top users by activity score
        
        Args:
            limit: Number of users to return
            
        Returns:
            List of user profiles ordered by activity score
        """
        top_users = UserProfile.objects.select_related('user').order_by('-activity_score')[:limit]
        
        leaderboard = []
        for i, profile in enumerate(top_users, 1):
            leaderboard.append({
                'rank': i,
                'user': profile.user,
                'activity_score': profile.activity_score,
                'revenue_share_rate': profile.revenue_share_rate,
                'lifetime_earnings': profile.lifetime_earnings,
                'available_balance': profile.available_balance
            })
        
        return leaderboard
    
    @staticmethod
    def get_user_activity_summary(user: User) -> Dict[str, Any]:
        """
        Get comprehensive activity summary for a user
        
        Args:
            user: The user to get summary for
            
        Returns:
            Dict with activity summary
        """
        profile = user.profile
        
        # Get activity metrics
        current_metrics = ActivityMetricsService.calculate_user_activity_score(user)
        
        # Get comparison metrics (last 30 days vs previous 30 days)
        previous_metrics = ActivityMetricsService.calculate_user_activity_score(user, days_back=60)
        
        # Calculate trends
        trends = {}
        for metric in current_metrics['metrics']:
            current_val = current_metrics['metrics'][metric]
            # For previous period, we'd need to calculate differently
            # This is a simplified version
            trends[metric] = {
                'current': current_val,
                'trend': 'stable'  # Would calculate actual trend
            }
        
        # Get recent activity
        recent_transactions = WalletTransaction.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(days=7)
        ).order_by('-created_at')[:5]
        
        return {
            'user': user,
            'profile': profile,
            'current_metrics': current_metrics,
            'trends': trends,
            'recent_transactions': recent_transactions,
            'leaderboard_rank': ActivityMetricsService._get_user_rank(user),
            'next_score_threshold': ActivityMetricsService._get_next_threshold(profile.activity_score)
        }
    
    @staticmethod
    def _get_user_rank(user: User) -> int:
        """Get user's rank in activity leaderboard"""
        higher_scores = UserProfile.objects.filter(
            activity_score__gt=user.profile.activity_score
        ).count()
        return higher_scores + 1
    
    @staticmethod
    def _get_next_threshold(current_score: Decimal) -> Dict[str, Any]:
        """Get next activity score threshold and benefits"""
        thresholds = [
            {'score': Decimal('2.00'), 'rate': Decimal('0.1625'), 'description': 'Regular User'},
            {'score': Decimal('3.00'), 'rate': Decimal('0.175'), 'description': 'Active User'},
            {'score': Decimal('4.00'), 'rate': Decimal('0.1875'), 'description': 'Power User'},
            {'score': Decimal('5.00'), 'rate': Decimal('0.20'), 'description': 'Elite User'},
        ]
        
        for threshold in thresholds:
            if current_score < threshold['score']:
                return {
                    'next_score': threshold['score'],
                    'next_rate': threshold['rate'],
                    'next_description': threshold['description'],
                    'points_needed': threshold['score'] - current_score
                }
        
        return {
            'next_score': None,
            'next_rate': None,
            'next_description': 'Maximum Level Achieved',
            'points_needed': Decimal('0.00')
        }


class ActivityTracker:
    """Helper class to track user activities in real-time"""
    
    @staticmethod
    def track_affiliate_click(user: User, affiliate_link: AffiliateLink) -> None:
        """Track when user clicks an affiliate link"""
        try:
            # Could store in a separate activity log table
            # For now, we'll update the activity score periodically
            
            # Update activity score if it's been a while
            ActivityMetricsService.update_user_activity_score(user, force_update=False)
            
            logger.info(f"Tracked affiliate click for {user.email}: {affiliate_link.platform}")
            
        except Exception as e:
            logger.error(f"Error tracking affiliate click: {e}")
    
    @staticmethod
    def track_conversion(user: User, affiliate_link: AffiliateLink, amount: Decimal) -> None:
        """Track when user's affiliate action converts"""
        try:
            # Update activity score on conversion
            ActivityMetricsService.update_user_activity_score(user, force_update=True)
            
            logger.info(f"Tracked conversion for {user.email}: ${amount} from {affiliate_link.platform}")
            
        except Exception as e:
            logger.error(f"Error tracking conversion: {e}")
    
    @staticmethod
    def track_search_query(user: User, query: str) -> None:
        """Track when user performs a search"""
        try:
            # Could implement search tracking here
            # For now, this is a placeholder
            
            logger.info(f"Tracked search for {user.email}: {query}")
            
        except Exception as e:
            logger.error(f"Error tracking search: {e}") 