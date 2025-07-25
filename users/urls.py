from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Payout Management Dashboard URLs
    path('admin/payout-queue/', views.payout_queue_dashboard, name='payout_queue_dashboard'),
    path('admin/payout-eligibility/', views.payout_eligibility_checker, name='payout_eligibility_checker'),
    path('admin/batch-payout/', views.batch_payout_processor, name='batch_payout_processor'),
    path('admin/payout-analytics/', views.payout_analytics_dashboard, name='payout_analytics_dashboard'),
    
    # AJAX endpoints
    path('admin/ajax/payout-action/', views.ajax_payout_action, name='ajax_payout_action'),
    path('admin/ajax/eligibility-action/', views.ajax_eligibility_action, name='ajax_eligibility_action'),
    path('admin/ajax/task-status/<str:task_id>/', views.ajax_task_status, name='ajax_task_status'),
] 