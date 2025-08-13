from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django_q.tasks import async_task
from .models import Quote, QuoteItem, ProductMatch
from .forms import QuoteUploadForm
import logging
import json
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
import mimetypes
import os
from graphql_jwt.shortcuts import get_user_by_token
from graphql_jwt.exceptions import JSONWebTokenError

logger = logging.getLogger(__name__)
User = get_user_model()

@login_required
def upload_quote(request):
    """Simple view for testing quote uploads"""
    
    if request.method == 'POST':
        form = QuoteUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            # Create quote
            quote = form.save(commit=False)
            quote.user = request.user
            quote.original_filename = request.FILES['pdf_file'].name
            quote.status = 'parsing'
            quote.demo_mode_enabled = form.cleaned_data.get('demo_mode', False)
            quote.save()
            
            # Start processing
            try:
                task_id = async_task(
                    'quotes.tasks.process_quote_pdf',
                    quote.id,
                    group='quote_processing',
                    timeout=300
                )
                
                quote.openai_task_id = task_id
                quote.save()
                
                messages.success(
                    request, 
                    f'Quote uploaded successfully! Processing started. Quote ID: {quote.id}'
                )
                
                return redirect('quotes:detail', quote_id=quote.id)
                
            except Exception as e:
                quote.status = 'error'
                quote.parsing_error = str(e)
                quote.save()
                
                messages.error(request, f'Error starting processing: {str(e)}')
        
        else:
            messages.error(request, 'Please correct the errors below.')
    
    else:
        form = QuoteUploadForm()
    
    return render(request, 'quotes/upload.html', {
        'form': form,
        'title': 'Upload Quote for Analysis'
    })

@login_required
def quote_detail(request, quote_id):
    """View quote details and processing results"""
    
    quote = get_object_or_404(Quote, id=quote_id, user=request.user)
    
    # Get quote items with matches
    items = quote.items.prefetch_related('matches__product__manufacturer').all()
    
    # Calculate stats
    total_items = items.count()
    matched_items = items.filter(matches__isnull=False).distinct().count()
    demo_products = ProductMatch.objects.filter(
        quote_item__quote=quote,
        demo_generated_product=True
    ).count()
    
    context = {
        'quote': quote,
        'items': items,
        'total_items': total_items,
        'matched_items': matched_items,
        'demo_products': demo_products,
        'title': f'Quote Analysis - {quote.vendor_company or "Quote"} #{quote.id}'
    }
    
    return render(request, 'quotes/detail.html', context)

@login_required
def quote_list(request):
    """List all quotes for the current user"""
    
    quotes = Quote.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'quotes': quotes,
        'title': 'My Quotes'
    }
    
    return render(request, 'quotes/list.html', context)

@login_required
@require_http_methods(["POST"])
def rematch_quote(request, quote_id):
    """Re-run product matching for a quote"""
    
    quote = get_object_or_404(Quote, id=quote_id, user=request.user)
    
    demo_mode = request.POST.get('demo_mode') == 'true'
    
    try:
        # Clear existing matches
        ProductMatch.objects.filter(quote_item__quote=quote).delete()
        
        # Update demo mode
        quote.demo_mode_enabled = demo_mode
        quote.status = 'matching'
        quote.save()
        
        # Start matching task
        task_id = async_task(
            'quotes.tasks.match_quote_products',
            quote.id,
            demo_mode,
            group='quote_matching',
            timeout=180
        )
        
        messages.success(request, 'Product matching started!')
        
        return JsonResponse({
            'success': True,
            'message': 'Product matching started',
            'task_id': task_id
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
def quote_status(request, quote_id):
    """Get quote processing status (AJAX endpoint)"""
    
    quote = get_object_or_404(Quote, id=quote_id, user=request.user)
    
    # Calculate progress
    total_items = quote.items.count()
    matched_items = quote.items.filter(matches__isnull=False).distinct().count()
    
    if total_items > 0:
        progress = int((matched_items / total_items) * 100)
    else:
        progress = 0
    
    # Determine current step and estimated time
    step_info = {
        'uploading': {'message': 'Uploading file', 'estimated_seconds': 5},
        'parsing': {'message': 'Parsing PDF with AI', 'estimated_seconds': 25},
        'matching': {'message': 'Matching products', 'estimated_seconds': 15},
        'completed': {'message': 'Analysis complete', 'estimated_seconds': 0},
        'error': {'message': 'Error occurred', 'estimated_seconds': 0}
    }
    
    current_step_info = step_info.get(quote.status, {'message': 'Processing...', 'estimated_seconds': 10})
    current_step = current_step_info['message']
    
    # Calculate estimated time remaining
    estimated_time_remaining = None
    if quote.status in ['uploading', 'parsing', 'matching']:
        from django.utils import timezone
        processing_time = (timezone.now() - quote.created_at).total_seconds()
        
        # Adjust estimate based on how long it's been processing
        base_estimate = current_step_info['estimated_seconds']
        
        if quote.status == 'parsing':
            # If parsing is taking longer, increase estimate
            if processing_time > 10:  # Been parsing for more than 10 seconds
                base_estimate = max(base_estimate, int(processing_time * 1.2))
        elif quote.status == 'matching':
            # Estimate based on number of items
            if total_items > 0:
                base_estimate = min(30, max(10, total_items * 2))  # 2 seconds per item, max 30s
        
        estimated_time_remaining = max(5, base_estimate - int(processing_time))
    
    return JsonResponse({
        'status': quote.status,
        'progress': progress,
        'current_step': current_step,
        'estimated_time_remaining': estimated_time_remaining,
        'error_message': quote.parsing_error if quote.status == 'error' else None,
        'total_items': total_items,
        'matched_items': matched_items
    })


def jwt_authentication_required(view_func):
    """Custom decorator for JWT authentication in REST views using graphql-jwt"""
    def wrapper(request, *args, **kwargs):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        # Debug logging
        logger.info(f"🔍 REST API authentication attempt")
        logger.info(f"🔍 Auth header: {auth_header[:50]}..." if auth_header else "🔍 No auth header")
        logger.info(f"🔍 All headers: {dict(request.META)}")
        
        if not auth_header:
            return JsonResponse({
                'success': False,
                'message': 'Authorization header is required',
                'errors': ['Missing Authorization header']
            }, status=401)
        
        # Check for JWT prefix
        if not auth_header.startswith('JWT '):
            return JsonResponse({
                'success': False,
                'message': 'Invalid authorization format. Use: JWT <token>',
                'errors': ['Invalid authorization format']
            }, status=401)
        
        # Extract token
        token = auth_header[4:]  # Remove 'JWT ' prefix
        
        try:
            # Use graphql-jwt's built-in token verification
            user = get_user_by_token(token)
            
            if not user:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid token or user not found',
                    'errors': ['Token validation failed']
                }, status=401)
            
            if not user.is_active:
                return JsonResponse({
                    'success': False,
                    'message': 'User account is disabled',
                    'errors': ['Account disabled']
                }, status=401)
            
            # Attach user to request
            request.user = user
            
            logger.info(f"✅ JWT authentication successful for user: {user.id}")
            return view_func(request, *args, **kwargs)
            
        except JSONWebTokenError as e:
            logger.warning(f"❌ JWT authentication failed: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': 'Invalid token',
                'errors': [str(e)]
            }, status=401)
        except Exception as e:
            logger.error(f"❌ Unexpected error in JWT authentication: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': 'Authentication error',
                'errors': [str(e)]
            }, status=401)
    
    return wrapper


@csrf_exempt
@require_http_methods(["POST"])
@jwt_authentication_required
def upload_quote_rest(request):
    """REST API endpoint for quote uploads - matches GraphQL mutation format"""
    
    try:
        # Validate file upload
        if 'file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'message': 'No file provided',
                'quote': None,
                'errors': ['File is required']
            }, status=400)
        
        uploaded_file = request.FILES['file']
        
        # Validate file type
        if not uploaded_file.name.lower().endswith('.pdf'):
            return JsonResponse({
                'success': False,
                'message': 'Only PDF files are allowed',
                'quote': None,
                'errors': ['Invalid file type. Only PDF files are supported.']
            }, status=400)
        
        # Validate file size (10MB limit)
        max_size = 10 * 1024 * 1024  # 10MB
        if uploaded_file.size > max_size:
            return JsonResponse({
                'success': False,
                'message': 'File size exceeds 10MB limit',
                'quote': None,
                'errors': ['File too large. Maximum size is 10MB.']
            }, status=400)
        
        # Validate mime type
        mime_type, _ = mimetypes.guess_type(uploaded_file.name)
        if mime_type != 'application/pdf':
            return JsonResponse({
                'success': False,
                'message': 'Invalid file format',
                'quote': None,
                'errors': ['File must be a valid PDF']
            }, status=400)
        
        # Get demo mode from form data
        demo_mode = request.POST.get('demoMode', 'false').lower() == 'true'
        
        # Create quote
        quote = Quote.objects.create(
            user=request.user,
            pdf_file=uploaded_file,
            original_filename=uploaded_file.name,
            status='uploading',
            demo_mode_enabled=demo_mode
        )
        
        # Start background processing
        async_task(
            'quotes.tasks.process_quote_pdf',
            quote.id,
            task_name=f'quote_processing',
            group='quote_processing'
        )
        
        # Update status to parsing
        quote.status = 'parsing'
        quote.save()
        
        logger.info(f"✅ Quote {quote.id} uploaded via REST API by user {request.user.id}")
        
        # Return response in same format as GraphQL mutation
        return JsonResponse({
            'success': True,
            'message': 'Quote uploaded successfully and processing started',
            'quote': {
                'id': str(quote.id),
                'status': quote.status,
                'originalFilename': quote.original_filename,
                'createdAt': quote.created_at.isoformat(),
                'demoModeEnabled': quote.demo_mode_enabled
            },
            'errors': []
        }, status=201)
        
    except Exception as e:
        logger.error(f"❌ Error in REST quote upload: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'Upload failed due to server error',
            'quote': None,
            'errors': [str(e)]
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def test_jwt_token(request):
    """Debug endpoint to test JWT token validation"""
    try:
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header.startswith('JWT '):
            return JsonResponse({
                'valid': False,
                'error': 'Invalid auth header format',
                'received_header': auth_header[:50] + '...' if len(auth_header) > 50 else auth_header
            })
        
        token = auth_header[4:]
        
        # Test with graphql-jwt
        try:
            user = get_user_by_token(token)
            return JsonResponse({
                'valid': True,
                'user_id': user.id if user else None,
                'user_email': user.email if user else None,
                'token_preview': token[:20] + '...'
            })
        except JSONWebTokenError as e:
            return JsonResponse({
                'valid': False,
                'error': f'JWT Error: {str(e)}',
                'token_preview': token[:20] + '...'
            })
    except Exception as e:
        return JsonResponse({
            'valid': False,
            'error': f'General error: {str(e)}'
        })