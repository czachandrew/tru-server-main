from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from datetime import timedelta, datetime
from decimal import Decimal
import json
import csv

from .models import User, UserProfile, PayoutRequest, WalletTransaction
from .services import WalletService
from .tasks import PayoutTaskManager
from .mock_payout_service import PayoutProcessor


@staff_member_required
@ensure_csrf_cookie
def payout_queue_dashboard(request):
    """
    Comprehensive payout queue dashboard for admin management
    """
    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    priority_filter = request.GET.get('priority', 'all')
    method_filter = request.GET.get('method', 'all')
    days_filter = request.GET.get('days', 'all')
    
    # Base queryset
    payouts = PayoutRequest.objects.select_related(
        'user', 'user__profile', 'approved_by', 'processed_by', 'wallet_transaction'
    ).order_by('-requested_at')
    
    # Apply filters
    if status_filter != 'all':
        payouts = payouts.filter(status=status_filter)
    
    if priority_filter != 'all':
        payouts = payouts.filter(priority=priority_filter)
    
    if method_filter != 'all':
        payouts = payouts.filter(payout_method=method_filter)
    
    if days_filter != 'all':
        if days_filter == '1':
            payouts = payouts.filter(requested_at__gte=timezone.now() - timedelta(days=1))
        elif days_filter == '7':
            payouts = payouts.filter(requested_at__gte=timezone.now() - timedelta(days=7))
        elif days_filter == '30':
            payouts = payouts.filter(requested_at__gte=timezone.now() - timedelta(days=30))
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(payouts, 50)  # Show 50 payouts per page
    page_number = request.GET.get('page')
    payout_list = paginator.get_page(page_number)
    
    # Calculate summary statistics
    stats = calculate_payout_stats()
    
    # Urgent payouts (pending > 7 days)
    urgent_payouts = PayoutRequest.objects.filter(
        status='pending',
        requested_at__lte=timezone.now() - timedelta(days=7)
    ).count()
    
    # Users needing eligibility review
    pending_eligibility = UserProfile.objects.filter(
        payout_status='pending_verification',
        available_balance__gte=10.00  # Above minimum cashout
    ).count()
    
    context = {
        'payout_list': payout_list,
        'stats': stats,
        'urgent_payouts': urgent_payouts,
        'pending_eligibility': pending_eligibility,
        'filters': {
            'status': status_filter,
            'priority': priority_filter,
            'method': method_filter,
            'days': days_filter,
        },
        'status_choices': PayoutRequest.PAYOUT_STATUS_CHOICES,
        'priority_choices': PayoutRequest.PRIORITY_CHOICES,
        'method_choices': PayoutRequest.PAYOUT_METHOD_CHOICES,
    }
    
    return render(request, 'admin/users/payout_queue_dashboard.html', context)


@staff_member_required
def payout_eligibility_checker(request):
    """
    Check and manage user payout eligibility
    """
    # Get users who might need eligibility review
    users_to_review = UserProfile.objects.filter(
        Q(payout_status='pending_verification') |
        Q(available_balance__gte=10.00, payout_status='suspended')
    ).select_related('user').order_by('-available_balance')
    
    # Calculate eligibility for each user
    eligibility_results = []
    for profile in users_to_review:
        eligibility = check_user_payout_eligibility(profile.user)
        eligibility_results.append({
            'profile': profile,
            'eligibility': eligibility
        })
    
    context = {
        'eligibility_results': eligibility_results,
        'total_users': users_to_review.count(),
        'eligible_count': sum(1 for r in eligibility_results if r['eligibility']['is_eligible']),
    }
    
    return render(request, 'admin/users/payout_eligibility_checker.html', context)


@staff_member_required
def batch_payout_processor(request):
    """
    Batch processing interface for multiple payouts
    """
    if request.method == 'POST':
        action = request.POST.get('action')
        payout_ids = request.POST.getlist('payout_ids')
        
        if not payout_ids:
            messages.error(request, "No payouts selected")
            return redirect('users:payout_queue_dashboard')
        
        # Get selected payouts
        payouts = PayoutRequest.objects.filter(id__in=payout_ids)
        
        if action == 'approve':
            return handle_batch_approval(request, payouts)
        elif action == 'reject':
            return handle_batch_rejection(request, payouts)
        elif action == 'process':
            return handle_batch_processing(request, payouts)
        elif action == 'export':
            return export_payouts_csv(request, payouts)
    
    # GET request - show batch processing interface
    pending_payouts = PayoutRequest.objects.filter(status='pending').select_related(
        'user', 'user__profile'
    ).order_by('-priority', '-requested_at')
    
    approved_payouts = PayoutRequest.objects.filter(status='approved').select_related(
        'user', 'user__profile'
    ).order_by('-requested_at')
    
    context = {
        'pending_payouts': pending_payouts,
        'approved_payouts': approved_payouts,
    }
    
    return render(request, 'admin/users/batch_payout_processor.html', context)


@staff_member_required
def payout_analytics_dashboard(request):
    """
    Analytics and reporting dashboard for payouts
    """
    # Date range for analytics
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)  # Last 30 days
    
    # Custom date range if provided
    if request.GET.get('start_date'):
        start_date = datetime.strptime(request.GET.get('start_date'), '%Y-%m-%d')
        start_date = timezone.make_aware(start_date)
    
    if request.GET.get('end_date'):
        end_date = datetime.strptime(request.GET.get('end_date'), '%Y-%m-%d')
        end_date = timezone.make_aware(end_date)
    
    # Generate analytics data
    analytics = generate_payout_analytics(start_date, end_date)
    
    context = {
        'analytics': analytics,
        'start_date': start_date.date(),
        'end_date': end_date.date(),
    }
    
    return render(request, 'admin/users/payout_analytics_dashboard.html', context)


@staff_member_required
@require_http_methods(["POST"])
def ajax_payout_action(request):
    """
    Handle AJAX actions for individual payouts
    """
    payout_id = request.POST.get('payout_id')
    action = request.POST.get('action')
    
    try:
        payout = PayoutRequest.objects.get(id=payout_id)
        
        if action == 'approve':
            notes = request.POST.get('notes', 'Quick approval via dashboard')
            payout.approve(request.user, notes)
            
            # Queue for background processing
            priority = 'high' if payout.priority in ['high', 'urgent'] else 'normal'
            task_id = PayoutTaskManager.queue_payout_processing(payout.id, priority)
            
            return JsonResponse({
                'success': True, 
                'message': f'Payout #{payout.id} approved and queued for processing',
                'new_status': payout.status,
                'task_id': task_id,
                'processing_note': 'Payout will be processed in the background'
            })
        
        elif action == 'reject':
            reason = request.POST.get('reason', 'Rejected via dashboard')
            payout.reject(request.user, reason)
            return JsonResponse({
                'success': True, 
                'message': f'Payout #{payout.id} rejected',
                'new_status': payout.status
            })
        
        elif action == 'process':
            if payout.status != 'approved':
                return JsonResponse({
                    'success': False, 
                    'message': f'Payout #{payout.id} must be approved before processing'
                })
            
            # Queue for immediate background processing
            task_id = PayoutTaskManager.queue_payout_processing(payout.id, 'high')
            
            return JsonResponse({
                'success': True, 
                'message': f'Payout #{payout.id} queued for immediate processing',
                'new_status': 'processing',
                'task_id': task_id,
                'processing_note': 'Processing will complete in 3-10 seconds'
            })
        
        elif action == 'retry':
            if payout.can_retry:
                # Queue for retry processing
                task_id = PayoutTaskManager.queue_payout_processing(payout.id, 'high')
                
                return JsonResponse({
                    'success': True, 
                    'message': f'Payout #{payout.id} queued for retry processing',
                    'new_status': 'processing',
                    'task_id': task_id,
                    'processing_note': 'Retry will complete in 3-10 seconds'
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'message': 'Payout cannot be retried'
                })
        
        else:
            return JsonResponse({'success': False, 'message': 'Unknown action'})
    
    except PayoutRequest.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Payout not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@staff_member_required
@require_http_methods(["GET"])
def ajax_task_status(request, task_id):
    """
    Get status of a background task
    """
    try:
        status = PayoutTaskManager.get_task_status(task_id)
        return JsonResponse(status)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'message': 'Error checking task status'
        })


@staff_member_required
@require_http_methods(["POST"])
def ajax_eligibility_action(request):
    """
    Handle AJAX actions for user eligibility
    """
    user_id = request.POST.get('user_id')
    action = request.POST.get('action')
    
    try:
        user = User.objects.get(id=user_id)
        profile = user.profile
        
        if action == 'approve_eligibility':
            profile.payout_status = 'eligible'
            profile.save()
            return JsonResponse({
                'success': True, 
                'message': f'User {user.email} approved for payouts'
            })
        
        elif action == 'suspend_eligibility':
            reason = request.POST.get('reason', 'Suspended via dashboard')
            profile.payout_status = 'suspended'
            profile.save()
            return JsonResponse({
                'success': True, 
                'message': f'User {user.email} suspended from payouts'
            })
        
        else:
            return JsonResponse({'success': False, 'message': 'Unknown action'})
    
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# Helper functions
def calculate_payout_stats():
    """Calculate summary statistics for payouts"""
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    stats = {
        'total_pending': PayoutRequest.objects.filter(status='pending').count(),
        'total_approved': PayoutRequest.objects.filter(status='approved').count(),
        'total_processing': PayoutRequest.objects.filter(status='processing').count(),
        'total_completed_today': PayoutRequest.objects.filter(
            status='completed', 
            completed_at__date=today
        ).count(),
        'total_completed_week': PayoutRequest.objects.filter(
            status='completed', 
            completed_at__date__gte=week_ago
        ).count(),
        'amount_pending': PayoutRequest.objects.filter(
            status__in=['pending', 'approved', 'processing']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0'),
        'amount_completed_week': PayoutRequest.objects.filter(
            status='completed',
            completed_at__date__gte=week_ago
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0'),
    }
    
    # Calculate average processing time manually
    completed_payouts = PayoutRequest.objects.filter(
        status='completed',
        approved_at__isnull=False,
        completed_at__isnull=False
    )
    
    total_processing_time = 0
    count = 0
    for payout in completed_payouts:
        if payout.approved_at and payout.completed_at:
            processing_time = (payout.completed_at - payout.approved_at).total_seconds()
            total_processing_time += processing_time
            count += 1
    
    if count > 0:
        stats['avg_processing_time'] = total_processing_time / count
        stats['avg_processing_time_hours'] = round(stats['avg_processing_time'] / 3600, 1)
    else:
        stats['avg_processing_time'] = 0
        stats['avg_processing_time_hours'] = 0
    
    return stats


def check_user_payout_eligibility(user):
    """Check if a user is eligible for payouts"""
    profile = user.profile
    
    eligibility = {
        'is_eligible': True,
        'issues': [],
        'recommendations': []
    }
    
    # Check minimum balance
    if profile.available_balance < profile.min_cashout_amount:
        eligibility['is_eligible'] = False
        eligibility['issues'].append(f"Balance ${profile.available_balance} below minimum ${profile.min_cashout_amount}")
    
    # Check account setup
    if profile.preferred_payout_method == 'stripe_bank' and not profile.stripe_connect_account_id:
        eligibility['issues'].append("No Stripe Connect account configured")
        eligibility['recommendations'].append("User needs to complete Stripe account setup")
    
    if profile.preferred_payout_method == 'paypal' and not profile.paypal_email:
        eligibility['issues'].append("No PayPal email configured")
        eligibility['recommendations'].append("User needs to add PayPal email")
    
    # Check recent activity
    recent_earnings = WalletTransaction.objects.filter(
        user=user,
        transaction_type__in=['EARNING_PROJECTED', 'EARNING_CONFIRMED'],
        created_at__gte=timezone.now() - timedelta(days=30)
    ).count()
    
    if recent_earnings == 0:
        eligibility['recommendations'].append("No recent affiliate activity")
    
    # Check for suspicious activity
    recent_payouts = PayoutRequest.objects.filter(
        user=user,
        requested_at__gte=timezone.now() - timedelta(days=7)
    ).count()
    
    if recent_payouts > 5:
        eligibility['issues'].append("High payout request frequency")
        eligibility['is_eligible'] = False
    
    # Final eligibility check
    if eligibility['issues']:
        eligibility['is_eligible'] = False
    
    return eligibility


def generate_payout_analytics(start_date, end_date):
    """Generate analytics data for the specified date range"""
    payouts = PayoutRequest.objects.filter(
        requested_at__range=[start_date, end_date]
    )
    
    analytics = {
        'total_requests': payouts.count(),
        'total_amount': payouts.aggregate(total=Sum('amount'))['total'] or Decimal('0'),
        'completed_amount': payouts.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0'),
        'pending_amount': payouts.filter(status='pending').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0'),
        'failed_amount': payouts.filter(status='failed').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0'),
        'by_status': payouts.values('status').annotate(
            count=Count('id'),
            amount=Sum('amount')
        ).order_by('status'),
        'by_method': payouts.values('payout_method').annotate(
            count=Count('id'),
            amount=Sum('amount')
        ).order_by('payout_method'),
        'by_priority': payouts.values('priority').annotate(
            count=Count('id'),
            amount=Sum('amount')
        ).order_by('priority'),
        'top_users': payouts.values(
            'user__email', 'user__first_name', 'user__last_name'
        ).annotate(
            request_count=Count('id'),
            total_amount=Sum('amount')
        ).order_by('-total_amount')[:10],
    }
    
    return analytics


def handle_batch_approval(request, payouts):
    """Handle batch approval of payouts"""
    approved_count = 0
    error_count = 0
    approved_ids = []
    
    for payout in payouts.filter(status='pending'):
        try:
            payout.approve(request.user, "Batch approval via dashboard")
            approved_count += 1
            approved_ids.append(payout.id)
        except Exception as e:
            error_count += 1
            messages.error(request, f"Error approving payout #{payout.id}: {str(e)}")
    
    # Queue approved payouts for background processing
    if approved_ids:
        task_id = PayoutTaskManager.queue_batch_processing(approved_ids)
        messages.success(request, f"Successfully approved {approved_count} payouts and queued for processing (Task: {task_id})")
    
    if error_count > 0:
        messages.warning(request, f"{error_count} payouts could not be approved")
    
    return redirect('users:payout_queue_dashboard')


def handle_batch_rejection(request, payouts):
    """Handle batch rejection of payouts"""
    reason = request.POST.get('rejection_reason', 'Batch rejection via dashboard')
    rejected_count = 0
    error_count = 0
    
    for payout in payouts.filter(status='pending'):
        try:
            payout.reject(request.user, reason)
            rejected_count += 1
        except Exception as e:
            error_count += 1
            messages.error(request, f"Error rejecting payout #{payout.id}: {str(e)}")
    
    if rejected_count > 0:
        messages.success(request, f"Successfully rejected {rejected_count} payouts")
    
    if error_count > 0:
        messages.warning(request, f"{error_count} payouts could not be rejected")
    
    return redirect('users:payout_queue_dashboard')


def handle_batch_processing(request, payouts):
    """Handle batch processing of approved payouts"""
    processed_count = 0
    error_count = 0
    payout_ids = []
    
    for payout in payouts.filter(status='approved'):
        try:
            processed_count += 1
            payout_ids.append(payout.id)
        except Exception as e:
            error_count += 1
            messages.error(request, f"Error queuing payout #{payout.id}: {str(e)}")
    
    # Queue approved payouts for immediate processing
    if payout_ids:
        task_id = PayoutTaskManager.queue_batch_processing(payout_ids)
        messages.success(request, f"Successfully queued {processed_count} payouts for immediate processing (Task: {task_id})")
    
    if error_count > 0:
        messages.warning(request, f"{error_count} payouts could not be queued")
    
    return redirect('users:payout_queue_dashboard')


def export_payouts_csv(request, payouts):
    """Export selected payouts to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payouts_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'User Email', 'Amount', 'Status', 'Method', 'Priority',
        'Requested Date', 'Approved Date', 'Completed Date', 'External Transaction ID'
    ])
    
    for payout in payouts:
        writer.writerow([
            payout.id,
            payout.user.email,
            payout.amount,
            payout.status,
            payout.get_payout_method_display(),
            payout.priority,
            payout.requested_at.strftime('%Y-%m-%d %H:%M'),
            payout.approved_at.strftime('%Y-%m-%d %H:%M') if payout.approved_at else '',
            payout.completed_at.strftime('%Y-%m-%d %H:%M') if payout.completed_at else '',
            payout.external_transaction_id or ''
        ])
    
    return response
