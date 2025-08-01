import graphene
from graphene_django import DjangoObjectType
from users.models import ReferralCode, Promotion, UserReferralCode, ReferralDisbursement, OrganizationVerification
from users.services import ReferralCodeService, OrganizationService


class ReferralCodeType(DjangoObjectType):
    """GraphQL type for ReferralCode"""
    is_valid = graphene.Boolean(description="Whether this code is currently valid for entry")
    promotion_status = graphene.String(description="Current status of the associated promotion")
    
    class Meta:
        model = ReferralCode
        fields = ('id', 'code', 'owner', 'is_active', 'created_at', 'expires_at')
    
    def resolve_is_valid(self, info):
        """Check if code is valid for entry"""
        try:
            promotion = self.promotion
            return (promotion and promotion.is_active and 
                   promotion.is_code_entry_open())
        except:
            return False
    
    def resolve_promotion_status(self, info):
        """Get promotion status"""
        try:
            return self.promotion.get_status_display()
        except:
            return "No Promotion"


class PromotionType(DjangoObjectType):
    """GraphQL type for Promotion"""
    status = graphene.String(description="Current status of the promotion")
    is_code_entry_open = graphene.Boolean(description="Whether users can still enter this code")
    is_purchase_period_open = graphene.Boolean(description="Whether purchases can still count for this promotion")
    user_count = graphene.Int(description="Number of users who have this code")
    
    class Meta:
        model = Promotion
        fields = ('id', 'organization', 'referral_code', 'start_date', 'code_entry_deadline', 
                 'end_date', 'is_active', 'total_allocations')
    
    def resolve_status(self, info):
        return self.get_status_display()
    
    def resolve_is_code_entry_open(self, info):
        return self.is_code_entry_open()
    
    def resolve_is_purchase_period_open(self, info):
        return self.is_purchase_period_open()
    
    def resolve_user_count(self, info):
        return self.referral_code.user_referral_codes.filter(is_active=True).count()


class UserReferralCodeType(DjangoObjectType):
    """GraphQL type for UserReferralCode"""
    organization_name = graphene.String(description="Name of the organization")
    promotion_status = graphene.String(description="Status of the associated promotion")
    allocation_percentage = graphene.Float(description="Percentage of user's earnings allocated to this code")
    
    class Meta:
        model = UserReferralCode
        fields = ('id', 'user', 'referral_code', 'is_active', 'added_at')
    
    def resolve_organization_name(self, info):
        return self.referral_code.owner.profile.organization_name
    
    def resolve_promotion_status(self, info):
        try:
            return self.referral_code.promotion.get_status_display()
        except:
            return "No Promotion"
    
    def resolve_allocation_percentage(self, info):
        return float(self.allocation_percentage)


class ReferralDisbursementType(DjangoObjectType):
    """GraphQL type for ReferralDisbursement"""
    organization_name = graphene.String(description="Name of the recipient organization")
    amount = graphene.Float(description="Disbursement amount")
    allocation_percentage = graphene.Float(description="Allocation percentage")
    
    class Meta:
        model = ReferralDisbursement
        fields = ('id', 'wallet_transaction', 'referral_code', 'recipient_user', 
                 'status', 'created_at', 'confirmed_at', 'paid_at')
    
    def resolve_organization_name(self, info):
        return self.recipient_user.profile.organization_name
    
    def resolve_amount(self, info):
        return float(self.amount)
    
    def resolve_allocation_percentage(self, info):
        return float(self.allocation_percentage)


class OrganizationVerificationType(DjangoObjectType):
    """GraphQL type for OrganizationVerification"""
    class Meta:
        model = OrganizationVerification
        fields = ('id', 'organization', 'verification_status', 'tax_id_verified', 
                 'address_verified', 'phone_verified', 'website_verified', 
                 'manual_verification_date', 'verified_by', 'verification_notes',
                 'contact_person_name', 'contact_person_role', 'created_at', 'updated_at')


class UserReferralSummaryType(graphene.ObjectType):
    """GraphQL type for user referral summary"""
    active_codes = graphene.List(UserReferralCodeType, description="User's active referral codes")
    total_giving = graphene.Float(description="Total amount given to organizations")
    potential_giving = graphene.Float(description="Potential amount from projected earnings")
    net_earnings = graphene.Float(description="Net earnings after giving")
    potential_net_earnings = graphene.Float(description="Potential net earnings including pending")
    user_allocation_percentage = graphene.Float(description="Percentage of earnings user keeps")
    allocations = graphene.JSONString(description="Detailed allocation breakdown")


class OrganizationSummaryType(graphene.ObjectType):
    """GraphQL type for organization summary"""
    active_promotions = graphene.JSONString(description="Active promotions with user counts")
    total_received = graphene.Float(description="Total amount received from users")
    pending_disbursements = graphene.Float(description="Pending disbursements")
    verification_status = graphene.String(description="Current verification status")


class ReferralCodeValidationResultType(graphene.ObjectType):
    """GraphQL type for referral code validation result"""
    is_valid = graphene.Boolean(description="Whether the code is valid")
    message = graphene.String(description="Validation message or error")
    referral_code = graphene.Field(ReferralCodeType, description="Referral code object if valid")
    organization_name = graphene.String(description="Organization name if valid")


class ReferralCodeInput(graphene.InputObjectType):
    """Input type for referral code operations"""
    code = graphene.String(required=True, description="Referral code to add")
    allocation_percentage = graphene.Float(description="Custom allocation percentage (optional)")


class CreateOrganizationInput(graphene.InputObjectType):
    """Input type for creating an organization"""
    email = graphene.String(required=True, description="Organization email")
    password = graphene.String(required=True, description="Organization password")
    organization_name = graphene.String(required=True, description="Organization name")
    organization_type = graphene.String(required=True, description="Type of organization")
    min_payout_amount = graphene.Float(description="Minimum payout amount (default: 10.00)")


class CreatePromotionInput(graphene.InputObjectType):
    """Input type for creating a promotion"""
    organization_id = graphene.ID(required=True, description="Organization ID")
    start_date = graphene.DateTime(required=True, description="When the promotion starts")
    is_active = graphene.Boolean(description="Whether to activate immediately (default: false)")
    custom_code = graphene.String(description="Custom referral code (optional)") 