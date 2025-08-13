import graphene
from graphene_file_upload.scalars import Upload
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from django_q.tasks import async_task
import uuid
import os
import mimetypes

from quotes.models import Quote, QuoteItem, ProductMatch
from ..types.quote import (
    QuoteType, QuoteUploadResponse, QuoteMatchResponse, 
    QuoteProcessingStatus
)

User = get_user_model()

class UploadQuote(graphene.Mutation):
    """Upload and process a PDF quote"""
    
    class Arguments:
        file = Upload(required=True, description="PDF file to upload")
        vendor_name = graphene.String(description="Optional vendor name hint")
        vendor_company = graphene.String(description="Optional vendor company hint")
        demo_mode = graphene.Boolean(
            default_value=False, 
            description="Enable demo mode for superior pricing"
        )
    
    # Return fields
    success = graphene.Boolean()
    message = graphene.String()
    quote = graphene.Field(QuoteType)
    errors = graphene.List(graphene.String)
    
    @staticmethod
    def mutate(root, info, file, vendor_name=None, vendor_company=None, demo_mode=False):
        """Handle quote upload mutation"""
        
        # Check authentication
        user = info.context.user
        if user.is_anonymous:
            return UploadQuote(
                success=False,
                message="Authentication required",
                errors=["You must be logged in to upload quotes"]
            )
        
        errors = []
        
        try:
            # Validate file
            if not file:
                return UploadQuote(
                    success=False,
                    message="No file provided",
                    errors=["File is required"]
                )
            
            # Check file size (10MB limit)
            max_size = 10 * 1024 * 1024  # 10MB
            if file.size > max_size:
                return UploadQuote(
                    success=False,
                    message="File too large",
                    errors=[f"File size must be less than {max_size // (1024*1024)}MB"]
                )
            
            # Check file type by extension and mime type
            file_extension = os.path.splitext(file.name)[1].lower()
            if file_extension != '.pdf':
                return UploadQuote(
                    success=False,
                    message="Invalid file type",
                    errors=["Only PDF files are allowed"]
                )
            
            # Additional mime type check
            mime_type, _ = mimetypes.guess_type(file.name)
            if mime_type != 'application/pdf':
                return UploadQuote(
                    success=False,
                    message="Invalid file type",
                    errors=["Only PDF files are allowed"]
                )
            
            # Create quote record
            quote = Quote.objects.create(
                user=user,
                vendor_name=vendor_name or '',
                vendor_company=vendor_company or '',
                original_filename=file.name,
                status='uploading',
                demo_mode_enabled=demo_mode,
                openai_task_id=str(uuid.uuid4())
            )
            
            # Save file
            file_path = f'quotes/{quote.id}/{file.name}'
            quote.pdf_file.save(file.name, file, save=True)
            
            # Update status to parsing
            quote.status = 'parsing'
            quote.save()
            
            # Queue OpenAI processing task
            task_id = async_task(
                'quotes.tasks.process_quote_pdf',
                quote.id,
                group='quote_processing',
                timeout=300  # 5 minutes
            )
            
            # Update quote with task ID
            quote.openai_task_id = task_id
            quote.save()
            
            return UploadQuote(
                success=True,
                message="Quote uploaded successfully and processing started",
                quote=quote
            )
            
        except Exception as e:
            # Clean up quote if it was created
            if 'quote' in locals():
                quote.status = 'error'
                quote.parsing_error = str(e)
                quote.save()
            
            return UploadQuote(
                success=False,
                message="Upload failed",
                errors=[str(e)]
            )

class MatchQuoteProducts(graphene.Mutation):
    """Re-run product matching for a quote"""
    
    class Arguments:
        quote_id = graphene.ID(required=True, description="Quote ID to re-process")
        demo_mode = graphene.Boolean(
            default_value=False, 
            description="Enable demo mode for superior pricing"
        )
        force_rematch = graphene.Boolean(
            default_value=False,
            description="Force re-matching even if already completed"
        )
    
    # Return fields
    success = graphene.Boolean()
    message = graphene.String()
    quote = graphene.Field(QuoteType)
    matched_items = graphene.Int()
    total_items = graphene.Int()
    errors = graphene.List(graphene.String)
    
    @staticmethod
    def mutate(root, info, quote_id, demo_mode=False, force_rematch=False):
        """Handle quote product matching mutation"""
        
        # Check authentication
        user = info.context.user
        if user.is_anonymous:
            return MatchQuoteProducts(
                success=False,
                message="Authentication required",
                errors=["You must be logged in to match products"]
            )
        
        try:
            # Get quote
            quote = Quote.objects.get(id=quote_id)
            
            # Check permissions
            if not user.is_staff and quote.user != user:
                return MatchQuoteProducts(
                    success=False,
                    message="Permission denied",
                    errors=["You can only match products for your own quotes"]
                )
            
            # Check if quote has items
            if not quote.items.exists():
                return MatchQuoteProducts(
                    success=False,
                    message="No items to match",
                    errors=["Quote must be parsed before matching products"]
                )
            
            # Check if already processing (unless force_rematch)
            if quote.status == 'matching' and not force_rematch:
                return MatchQuoteProducts(
                    success=False,
                    message="Already processing",
                    errors=["Quote is already being processed"]
                )
            
            # Update demo mode if different
            if quote.demo_mode_enabled != demo_mode:
                quote.demo_mode_enabled = demo_mode
                quote.save()
            
            # Clear existing matches if force_rematch
            if force_rematch:
                ProductMatch.objects.filter(quote_item__quote=quote).delete()
            
            # Update status
            quote.status = 'matching'
            quote.save()
            
            # Queue matching task
            task_id = async_task(
                'quotes.tasks.match_quote_products',
                quote.id,
                demo_mode,
                group='quote_matching',
                timeout=180  # 3 minutes
            )
            
            # Get current counts
            total_items = quote.items.count()
            matched_items = quote.items.filter(matches__isnull=False).distinct().count()
            
            return MatchQuoteProducts(
                success=True,
                message="Product matching started",
                quote=quote,
                matched_items=matched_items,
                total_items=total_items
            )
            
        except Quote.DoesNotExist:
            return MatchQuoteProducts(
                success=False,
                message="Quote not found",
                errors=["Quote with the provided ID does not exist"]
            )
        except Exception as e:
            return MatchQuoteProducts(
                success=False,
                message="Matching failed",
                errors=[str(e)]
            )

class DeleteQuote(graphene.Mutation):
    """Delete a quote and all associated data"""
    
    class Arguments:
        quote_id = graphene.ID(required=True, description="Quote ID to delete")
    
    # Return fields
    success = graphene.Boolean()
    message = graphene.String()
    errors = graphene.List(graphene.String)
    
    @staticmethod
    def mutate(root, info, quote_id):
        """Handle quote deletion"""
        
        # Check authentication
        user = info.context.user
        if user.is_anonymous:
            return DeleteQuote(
                success=False,
                message="Authentication required",
                errors=["You must be logged in to delete quotes"]
            )
        
        try:
            # Get quote
            quote = Quote.objects.get(id=quote_id)
            
            # Check permissions
            if not user.is_staff and quote.user != user:
                return DeleteQuote(
                    success=False,
                    message="Permission denied",
                    errors=["You can only delete your own quotes"]
                )
            
            # Delete file if it exists
            if quote.pdf_file:
                try:
                    default_storage.delete(quote.pdf_file.name)
                except:
                    pass  # File might not exist or already deleted
            
            # Delete quote (cascade will handle related objects)
            quote.delete()
            
            return DeleteQuote(
                success=True,
                message="Quote deleted successfully"
            )
            
        except Quote.DoesNotExist:
            return DeleteQuote(
                success=False,
                message="Quote not found",
                errors=["Quote with the provided ID does not exist"]
            )
        except Exception as e:
            return DeleteQuote(
                success=False,
                message="Deletion failed",
                errors=[str(e)]
            )

class UpdateQuoteMetadata(graphene.Mutation):
    """Update quote metadata (vendor info, etc.)"""
    
    class Arguments:
        quote_id = graphene.ID(required=True)
        vendor_name = graphene.String()
        vendor_company = graphene.String()
        quote_number = graphene.String()
        quote_date = graphene.Date()
    
    # Return fields
    success = graphene.Boolean()
    message = graphene.String()
    quote = graphene.Field(QuoteType)
    errors = graphene.List(graphene.String)
    
    @staticmethod
    def mutate(root, info, quote_id, **kwargs):
        """Handle quote metadata update"""
        
        # Check authentication
        user = info.context.user
        if user.is_anonymous:
            return UpdateQuoteMetadata(
                success=False,
                message="Authentication required",
                errors=["You must be logged in to update quotes"]
            )
        
        try:
            # Get quote
            quote = Quote.objects.get(id=quote_id)
            
            # Check permissions
            if not user.is_staff and quote.user != user:
                return UpdateQuoteMetadata(
                    success=False,
                    message="Permission denied",
                    errors=["You can only update your own quotes"]
                )
            
            # Update fields
            updated_fields = []
            for field, value in kwargs.items():
                if value is not None and hasattr(quote, field):
                    setattr(quote, field, value)
                    updated_fields.append(field)
            
            if updated_fields:
                quote.save()
                message = f"Updated: {', '.join(updated_fields)}"
            else:
                message = "No changes made"
            
            return UpdateQuoteMetadata(
                success=True,
                message=message,
                quote=quote
            )
            
        except Quote.DoesNotExist:
            return UpdateQuoteMetadata(
                success=False,
                message="Quote not found",
                errors=["Quote with the provided ID does not exist"]
            )
        except Exception as e:
            return UpdateQuoteMetadata(
                success=False,
                message="Update failed",
                errors=[str(e)]
            )

# Mutation class that groups all quote mutations
class QuoteMutation(graphene.ObjectType):
    upload_quote = UploadQuote.Field()
    match_quote_products = MatchQuoteProducts.Field()
    delete_quote = DeleteQuote.Field()
    update_quote_metadata = UpdateQuoteMetadata.Field()
