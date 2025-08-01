import graphene
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from users.models import ReferralCode, Promotion, UserReferralCode, ReferralDisbursement
from users.services import ReferralCodeService, OrganizationService
from ..types.referral import (
    ReferralCodeType, PromotionType, UserReferralCodeType,
    ReferralCodeValidationResultType, ReferralCodeInput, CreateOrganizationInput, CreatePromotionInput
)

User = get_user_model()


class AddReferralCodeMutation(graphene.Mutation):
    """Mutation to add a referral code to the current user"""
    
    class Arguments:
        input = ReferralCodeInput(required=True)
    
    success = graphene.Boolean(description="Whether the operation was successful")
    message = graphene.String(description="Success or error message")
    user_referral_code = graphene.Field(UserReferralCodeType, description="Created user referral code")
    new_allocations = graphene.JSONString(description="Updated allocation percentages")
    
    def mutate(self, info, input):
        user = info.context.user
        if not user.is_authenticated:
            return AddReferralCodeMutation(
                success=False,
                message="Authentication required",
                user_referral_code=None,
                new_allocations=None
            )
        
        try:
            # Add the referral code
            user_code = ReferralCodeService.add_user_referral_code(
                user=user,
                referral_code=input.code,
                allocation_percentage=input.allocation_percentage
            )
            
            # Get updated allocations
            allocations = ReferralCodeService.calculate_user_allocations(user)
            
            return AddReferralCodeMutation(
                success=True,
                message=f"Successfully added referral code {input.code}",
                user_referral_code=user_code,
                new_allocations=allocations
            )
            
        except ValidationError as e:
            return AddReferralCodeMutation(
                success=False,
                message=str(e),
                user_referral_code=None,
                new_allocations=None
            )
        except Exception as e:
            return AddReferralCodeMutation(
                success=False,
                message=f"Error adding referral code: {str(e)}",
                user_referral_code=None,
                new_allocations=None
            )


class RemoveReferralCodeMutation(graphene.Mutation):
    """Mutation to remove a referral code from the current user"""
    
    class Arguments:
        referral_code_id = graphene.ID(required=True, description="ID of the UserReferralCode to remove")
    
    success = graphene.Boolean(description="Whether the operation was successful")
    message = graphene.String(description="Success or error message")
    new_allocations = graphene.JSONString(description="Updated allocation percentages")
    
    def mutate(self, info, referral_code_id):
        user = info.context.user
        if not user.is_authenticated:
            return RemoveReferralCodeMutation(
                success=False,
                message="Authentication required",
                new_allocations=None
            )
        
        try:
            # Remove the user referral code
            success = ReferralCodeService.remove_user_referral_code(user, referral_code_id)
            
            if success:
                # Get updated allocations
                allocations = ReferralCodeService.calculate_user_allocations(user)
                
                return RemoveReferralCodeMutation(
                    success=True,
                    message="Successfully removed referral code",
                    new_allocations=allocations
                )
            else:
                return RemoveReferralCodeMutation(
                    success=False,
                    message="Referral code not found or already removed",
                    new_allocations=None
                )
                
        except Exception as e:
            return RemoveReferralCodeMutation(
                success=False,
                message=f"Error removing referral code: {str(e)}",
                new_allocations=None
            )


class CreateOrganizationMutation(graphene.Mutation):
    """Mutation to create a new organization"""
    
    class Arguments:
        input = CreateOrganizationInput(required=True)
    
    success = graphene.Boolean(description="Whether the operation was successful")
    message = graphene.String(description="Success or error message")
    organization = graphene.Field('ecommerce_platform.graphql.types.user.UserType', description="Created organization")
    
    def mutate(self, info, input):
        try:
            # Check if user already exists
            if User.objects.filter(email=input.email).exists():
                return CreateOrganizationMutation(
                    success=False,
                    message="Organization with this email already exists",
                    organization=None
                )
            
            # Create organization
            organization, verification = OrganizationService.create_organization_with_verification(
                user=None,  # Will create new user
                organization_data={
                    'email': input.email,
                    'password': input.password,
                    'name': input.organization_name,
                    'type': input.organization_type,
                    'min_payout_amount': input.min_payout_amount or 10.00
                }
            )
            
            # Create the user account
            organization = User.objects.create_user(
                email=input.email,
                password=input.password
            )
            
            # Set up organization profile
            organization.profile.is_organization = True
            organization.profile.organization_name = input.organization_name
            organization.profile.organization_type = input.organization_type
            organization.profile.min_payout_amount = input.min_payout_amount or 10.00
            organization.profile.save()
            
            return CreateOrganizationMutation(
                success=True,
                message=f"Successfully created organization: {input.organization_name}",
                organization=organization
            )
            
        except Exception as e:
            return CreateOrganizationMutation(
                success=False,
                message=f"Error creating organization: {str(e)}",
                organization=None
            )


class CreatePromotionMutation(graphene.Mutation):
    """Mutation to create a new promotion for an organization"""
    
    class Arguments:
        input = CreatePromotionInput(required=True)
    
    success = graphene.Boolean(description="Whether the operation was successful")
    message = graphene.String(description="Success or error message")
    promotion = graphene.Field(PromotionType, description="Created promotion")
    referral_code = graphene.Field(ReferralCodeType, description="Generated referral code")
    
    def mutate(self, info, input):
        try:
            # Get organization
            organization = User.objects.get(id=input.organization_id)
            if not organization.profile.is_organization:
                return CreatePromotionMutation(
                    success=False,
                    message="User is not an organization",
                    promotion=None,
                    referral_code=None
                )
            
            # Create promotion
            if input.custom_code:
                referral_code = ReferralCode.create_for_organization(organization, input.custom_code)
            else:
                referral_code = ReferralCode.create_for_organization(organization)
            
            promotion = Promotion.objects.create(
                organization=organization,
                referral_code=referral_code,
                start_date=input.start_date,
                is_active=input.is_active or False
            )
            
            return CreatePromotionMutation(
                success=True,
                message=f"Successfully created promotion for {organization.profile.organization_name}",
                promotion=promotion,
                referral_code=referral_code
            )
            
        except User.DoesNotExist:
            return CreatePromotionMutation(
                success=False,
                message="Organization not found",
                promotion=None,
                referral_code=None
            )
        except Exception as e:
            return CreatePromotionMutation(
                success=False,
                message=f"Error creating promotion: {str(e)}",
                promotion=None,
                referral_code=None
            )


class ValidateReferralCodeMutation(graphene.Mutation):
    """Mutation to validate a referral code"""
    
    class Arguments:
        code = graphene.String(required=True, description="Referral code to validate")
    
    success = graphene.Boolean(description="Whether the operation was successful")
    message = graphene.String(description="Validation message")
    is_valid = graphene.Boolean(description="Whether the code is valid")
    referral_code = graphene.Field(ReferralCodeType, description="Referral code object if valid")
    organization_name = graphene.String(description="Organization name if valid")
    
    def mutate(self, info, code):
        try:
            is_valid, result = ReferralCodeService.validate_referral_code(code)
            
            if is_valid:
                referral_code = result
                return ValidateReferralCodeMutation(
                    success=True,
                    message="Code is valid",
                    is_valid=True,
                    referral_code=referral_code,
                    organization_name=referral_code.owner.profile.organization_name
                )
            else:
                return ValidateReferralCodeMutation(
                    success=False,
                    message=result,
                    is_valid=False,
                    referral_code=None,
                    organization_name=None
                )
                
        except Exception as e:
            return ValidateReferralCodeMutation(
                success=False,
                message=f"Validation error: {str(e)}",
                is_valid=False,
                referral_code=None,
                organization_name=None
            )


class ReferralMutations(graphene.ObjectType):
    """GraphQL mutations for referral system"""
    
    add_referral_code = AddReferralCodeMutation.Field(
        description="Add a referral code to the current user's active codes"
    )
    
    remove_referral_code = RemoveReferralCodeMutation.Field(
        description="Remove a referral code from the current user's active codes"
    )
    
    create_organization = CreateOrganizationMutation.Field(
        description="Create a new organization account"
    )
    
    create_promotion = CreatePromotionMutation.Field(
        description="Create a new promotion for an organization"
    )
    
    validate_referral_code = ValidateReferralCodeMutation.Field(
        description="Validate a referral code before adding it"
    ) 