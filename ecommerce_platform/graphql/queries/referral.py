import graphene
from django.contrib.auth import get_user_model
from users.models import ReferralCode, Promotion, UserReferralCode, ReferralDisbursement
from users.services import ReferralCodeService, OrganizationService
from ..types.referral import (
    ReferralCodeType, PromotionType, UserReferralCodeType, ReferralDisbursementType,
    UserReferralSummaryType, OrganizationSummaryType, ReferralCodeValidationResultType
)

User = get_user_model()


class ReferralQueries(graphene.ObjectType):
    """GraphQL queries for referral system"""
    
    # User referral queries
    my_referral_summary = graphene.Field(
        UserReferralSummaryType,
        description="Get current user's referral summary including active codes and giving statistics"
    )
    
    my_referral_codes = graphene.List(
        UserReferralCodeType,
        description="Get current user's active referral codes"
    )
    
    my_referral_disbursements = graphene.List(
        ReferralDisbursementType,
        description="Get current user's referral disbursements (giving history)"
    )
    
    # Organization queries
    organization_summary = graphene.Field(
        OrganizationSummaryType,
        organization_id=graphene.ID(required=True),
        description="Get organization's referral summary including promotions and earnings"
    )
    
    organization_promotions = graphene.List(
        PromotionType,
        organization_id=graphene.ID(required=True),
        description="Get all promotions for an organization"
    )
    
    organization_disbursements = graphene.List(
        ReferralDisbursementType,
        organization_id=graphene.ID(required=True),
        description="Get all disbursements received by an organization"
    )
    
    # Code validation
    validate_referral_code = graphene.Field(
        ReferralCodeValidationResultType,
        code=graphene.String(required=True),
        description="Validate a referral code and return details if valid"
    )
    
    # Public queries
    public_referral_codes = graphene.List(
        ReferralCodeType,
        description="Get all active referral codes (public information only)"
    )
    
    public_promotions = graphene.List(
        PromotionType,
        description="Get all active promotions (public information only)"
    )
    
    def resolve_my_referral_summary(self, info):
        """Get current user's referral summary"""
        user = info.context.user
        if not user.is_authenticated:
            return None
        
        try:
            summary_data = ReferralCodeService.get_user_referral_summary(user)
            return UserReferralSummaryType(
                active_codes=summary_data['active_codes'],
                total_giving=summary_data['total_giving'],
                potential_giving=summary_data['potential_giving'],
                net_earnings=summary_data['net_earnings'],
                potential_net_earnings=summary_data['potential_net_earnings'],
                user_allocation_percentage=summary_data['user_allocation_percentage'],
                allocations=summary_data['allocations']
            )
        except Exception as e:
            print(f"Error getting referral summary: {e}")
            return None
    
    def resolve_my_referral_codes(self, info):
        """Get current user's active referral codes"""
        user = info.context.user
        if not user.is_authenticated:
            return []
        
        return UserReferralCode.objects.filter(
            user=user,
            is_active=True
        ).select_related('referral_code', 'referral_code__owner', 'referral_code__promotion')
    
    def resolve_my_referral_disbursements(self, info):
        """Get current user's referral disbursements"""
        user = info.context.user
        if not user.is_authenticated:
            return []
        
        return ReferralDisbursement.objects.filter(
            wallet_transaction__user=user
        ).select_related('recipient_user', 'referral_code', 'wallet_transaction').order_by('-created_at')
    
    def resolve_organization_summary(self, info, organization_id):
        """Get organization's referral summary"""
        try:
            organization = User.objects.get(id=organization_id)
            if not organization.profile.is_organization:
                return None
            
            summary_data = OrganizationService.get_organization_summary(organization)
            return OrganizationSummaryType(
                active_promotions=summary_data['active_promotions'],
                total_received=summary_data['total_received'],
                pending_disbursements=summary_data['pending_disbursements'],
                verification_status=summary_data['verification_status']
            )
        except User.DoesNotExist:
            return None
        except Exception as e:
            print(f"Error getting organization summary: {e}")
            return None
    
    def resolve_organization_promotions(self, info, organization_id):
        """Get organization's promotions"""
        try:
            organization = User.objects.get(id=organization_id)
            if not organization.profile.is_organization:
                return []
            
            return Promotion.objects.filter(
                organization=organization
            ).select_related('referral_code').order_by('-start_date')
        except User.DoesNotExist:
            return []
    
    def resolve_organization_disbursements(self, info, organization_id):
        """Get organization's received disbursements"""
        try:
            organization = User.objects.get(id=organization_id)
            if not organization.profile.is_organization:
                return []
            
            return ReferralDisbursement.objects.filter(
                recipient_user=organization
            ).select_related('wallet_transaction', 'referral_code').order_by('-created_at')
        except User.DoesNotExist:
            return []
    
    def resolve_validate_referral_code(self, info, code):
        """Validate a referral code"""
        try:
            is_valid, result = ReferralCodeService.validate_referral_code(code)
            
            if is_valid:
                referral_code = result
                return ReferralCodeValidationResultType(
                    is_valid=True,
                    message="Code is valid",
                    referral_code=referral_code,
                    organization_name=referral_code.owner.profile.organization_name
                )
            else:
                return ReferralCodeValidationResultType(
                    is_valid=False,
                    message=result,
                    referral_code=None,
                    organization_name=None
                )
        except Exception as e:
            return ReferralCodeValidationResultType(
                is_valid=False,
                message=f"Validation error: {str(e)}",
                referral_code=None,
                organization_name=None
            )
    
    def resolve_public_referral_codes(self, info):
        """Get public referral codes (limited information)"""
        return ReferralCode.objects.filter(
            is_active=True
        ).select_related('owner', 'promotion')
    
    def resolve_public_promotions(self, info):
        """Get public promotions (limited information)"""
        return Promotion.objects.filter(
            is_active=True
        ).select_related('organization', 'referral_code') 