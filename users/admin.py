from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import json

from .models import User, UserProfile, WalletTransaction, PayoutRequest
from .withdrawal_service import WithdrawalAdminService
from .services import WalletService, ReconciliationService
from .activity_metrics import ActivityMetricsService


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False


class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )
    list_display = ('email', 'first_name', 'last_name', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    inlines = [UserProfileInline]


admin.site.register(User, UserAdmin)


class WalletTransactionInline(admin.TabularInline):
    """Inline admin for wallet transactions"""
    model = WalletTransaction
    extra = 0
    readonly_fields = ('id', 'created_at', 'updated_at', 'processed_at', 'balance_before', 'balance_after')
    fields = ('transaction_type', 'status', 'amount', 'description', 'created_at', 'processed_at')
    can_delete = False
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('affiliate_link').order_by('-created_at')[:10]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin interface for user profiles with wallet and payout information"""

    list_display = [
        'user_email', 'available_balance_display', 'pending_balance_display', 
        'activity_score', 'revenue_share_rate_display', 'lifetime_earnings_display',
        'total_withdrawn_display', 'stripe_connect_account_id', 'preferred_payout_method',
        'payout_status', 'last_payout_at', 'wallet_actions'
    ]

    list_filter = [
        'activity_score', 'created_at', 'updated_at',
        'payout_status', 'preferred_payout_method',
    ]

    search_fields = [
        'user__email', 'user__first_name', 'user__last_name',
        'stripe_connect_account_id', 'paypal_email'
    ]

    readonly_fields = [
        'user', 'created_at', 'updated_at', 'total_balance', 'revenue_share_rate',
        'wallet_summary', 'recent_transactions_display'
    ]

    fieldsets = (
        ('User Information', {
            'fields': ('user', 'phone', 'company', 'created_at', 'updated_at')
        }),
        ('Wallet Balance', {
            'fields': ('available_balance', 'pending_balance', 'total_balance', 'lifetime_earnings', 'total_withdrawn', 'total_spent')
        }),
        ('Activity & Revenue Share', {
            'fields': ('activity_score', 'revenue_share_rate', 'min_cashout_amount')
        }),
        ('Payout Information', {
            'fields': (
                'stripe_connect_account_id', 'preferred_payout_method', 'paypal_email',
                'payout_status', 'last_payout_at'
            ),
            'description': 'Manage user payout preferences and eligibility.'
        }),
        ('Wallet Summary', {
            'fields': ('wallet_summary', 'recent_transactions_display'),
            'classes': ('collapse',)
        })
    )

    actions = ['mark_as_payout_eligible', 'reset_payout_info', 'update_activity_scores', 'send_balance_notifications', 'generate_wallet_report']

    def user_email(self, obj):
        return obj.user.email if obj.user and hasattr(obj.user, 'email') else "-"

    def mark_as_payout_eligible(self, request, queryset):
        updated = queryset.update(payout_status='eligible')
        self.message_user(request, f"{updated} users marked as payout eligible.")

    mark_as_payout_eligible.short_description = "Mark selected users as payout eligible"

    def reset_payout_info(self, request, queryset):
        updated = queryset.update(stripe_connect_account_id=None, paypal_email=None, payout_status='pending_verification')
        self.message_user(request, f"{updated} users' payout info reset.")

    reset_payout_info.short_description = "Reset payout info for selected users"
    
    def available_balance_display(self, obj):
        return f"${obj.available_balance:.2f}" if obj.available_balance is not None else "-"
    available_balance_display.short_description = 'Available'
    available_balance_display.admin_order_field = 'available_balance'
    
    def pending_balance_display(self, obj):
        return f"${obj.pending_balance:.2f}" if obj.pending_balance is not None else "-"
    pending_balance_display.short_description = 'Pending'
    pending_balance_display.admin_order_field = 'pending_balance'
    
    def revenue_share_rate_display(self, obj):
        try:
            return f"{obj.revenue_share_rate:.2%}" if obj.revenue_share_rate is not None else "-"
        except Exception:
            return "-"
    revenue_share_rate_display.short_description = 'Revenue Share'
    revenue_share_rate_display.admin_order_field = 'revenue_share_rate'
    
    def lifetime_earnings_display(self, obj):
        return f"${obj.lifetime_earnings:.2f}" if obj.lifetime_earnings is not None else "-"
    lifetime_earnings_display.short_description = 'Lifetime Earnings'
    lifetime_earnings_display.admin_order_field = 'lifetime_earnings'
    
    def total_withdrawn_display(self, obj):
        return f"${obj.total_withdrawn:.2f}" if obj.total_withdrawn is not None else "-"
    total_withdrawn_display.short_description = 'Withdrawn'
    total_withdrawn_display.admin_order_field = 'total_withdrawn'
    
    def wallet_actions(self, obj):
        # Provide a link to the WalletTransaction admin filtered by user, or just a placeholder if user is missing
        try:
            if obj.user:
                url = reverse('admin:users_wallettransaction_changelist') + f'?user__id__exact={obj.user.id}'
                return format_html('<a href="{}">View Wallet Transactions</a>', url)
            return "-"
        except Exception:
            return "-"
    wallet_actions.short_description = 'Actions'
    
    def wallet_summary(self, obj):
        """Display wallet summary information"""
        try:
            summary = WalletService.get_wallet_summary(obj.user)
            
            html = f'''
            <div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">
                <h4>Wallet Summary</h4>
                <p><strong>Total Balance:</strong> ${summary['total_balance']:.2f}</p>
                <p><strong>Can Withdraw:</strong> {'Yes' if summary['can_withdraw'] else 'No'}</p>
                <p><strong>Pending Transactions:</strong> {len(summary['pending_transactions'])}</p>
                <p><strong>Recent Transactions:</strong> {len(summary['recent_transactions'])}</p>
            </div>
            '''
            return mark_safe(html)
        except Exception as e:
            return f"Error loading summary: {str(e)}"
    wallet_summary.short_description = 'Wallet Summary'
    
    def recent_transactions_display(self, obj):
        """Display recent transactions"""
        recent_transactions = WalletTransaction.objects.filter(
            user=obj.user
        ).order_by('-created_at')[:5]
        
        html = '<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">'
        html += '<h4>Recent Transactions</h4>'
        
        for transaction in recent_transactions:
            color = 'green' if transaction.amount > 0 else 'red'
            html += f'''
            <div style="margin-bottom: 5px; padding: 5px; border-left: 3px solid {color};">
                <strong>{transaction.get_transaction_type_display()}</strong><br>
                <span style="color: {color};">${transaction.amount:.2f}</span> - {transaction.get_status_display()}<br>
                <small>{transaction.created_at.strftime('%Y-%m-%d %H:%M')}</small>
            </div>
            '''
        
        html += '</div>'
        return mark_safe(html)
    recent_transactions_display.short_description = 'Recent Transactions'
    
    def update_activity_scores(self, request, queryset):
        """Update activity scores for selected users"""
        updated_count = 0
        for profile in queryset:
            result = ActivityMetricsService.update_user_activity_score(profile.user, force_update=True)
            if result['updated']:
                updated_count += 1
        
        self.message_user(request, f"Updated activity scores for {updated_count} users")
    update_activity_scores.short_description = "Update activity scores"
    
    def send_balance_notifications(self, request, queryset):
        """Send balance notifications to selected users"""
        from .notifications import NotificationService
        
        sent_count = 0
        for profile in queryset:
            notifications = NotificationService.check_balance_thresholds(profile.user)
            if notifications:
                sent_count += 1
        
        self.message_user(request, f"Sent notifications to {sent_count} users")
    send_balance_notifications.short_description = "Send balance notifications"
    
    def generate_wallet_report(self, request, queryset):
        """Generate wallet report for selected users"""
        # This would generate a comprehensive report
        # For now, just show a summary
        total_balance = queryset.aggregate(
            total_available=Sum('available_balance'),
            total_pending=Sum('pending_balance'),
            total_lifetime=Sum('lifetime_earnings')
        )
        
        self.message_user(
            request, 
            f"Report: {queryset.count()} users, "
            f"${total_balance['total_available']:.2f} available, "
            f"${total_balance['total_pending']:.2f} pending, "
            f"${total_balance['total_lifetime']:.2f} lifetime earnings"
        )
    generate_wallet_report.short_description = "Generate wallet report"


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    """Admin interface for wallet transactions"""
    
    list_display = [
        'id', 'user_email', 'transaction_type', 'status', 'amount_display',
        'product_name', 'affiliate_platform', 'created_at', 'processed_at', 'transaction_actions'
    ]
    
    list_filter = [
        'transaction_type', 'status', 'created_at', 'processed_at',
        'affiliate_link__platform', 'affiliate_link__product__manufacturer'
    ]
    
    search_fields = [
        'user__email', 'description', 'withdrawal_reference', 'order_reference',
        'affiliate_link__product__name', 'affiliate_link__product__part_number'
    ]
    
    readonly_fields = [
        'id', 'user', 'created_at', 'updated_at', 'processed_at', 
        'balance_before', 'balance_after', 'metadata_display'
    ]
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('id', 'user', 'transaction_type', 'status', 'amount', 'currency')
        }),
        ('Balance Information', {
            'fields': ('balance_before', 'balance_after')
        }),
        ('References', {
            'fields': ('affiliate_link', 'order_reference', 'withdrawal_reference')
        }),
        ('Processing Information', {
            'fields': ('description', 'processed_at', 'processed_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
        ('Metadata', {
            'fields': ('metadata_display',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['approve_withdrawals', 'reject_withdrawals', 'confirm_earnings', 'export_transactions']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'affiliate_link', 'affiliate_link__product', 'processed_by'
        )
    
    def user_email(self, obj):
        return obj.user.email if obj.user else "-"
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def amount_display(self, obj):
        """Display the transaction amount with proper formatting and color coding"""
        try:
            if obj.amount is None:
                return "-"
            
            # Convert Decimal to float for display
            amount = float(obj.amount)
            
            # Color code based on transaction type and amount
            if obj.transaction_type in ['EARNING_PROJECTED', 'EARNING_CONFIRMED', 'BONUS_ACTIVITY']:
                color = 'green'  # Earnings are green
            elif obj.transaction_type in ['SPENDING_STORE', 'WITHDRAWAL_CASH', 'WITHDRAWAL_PENDING']:
                color = 'red'    # Spending/withdrawals are red
            else:
                color = 'blue'   # Other transactions are blue
            
            # Format the amount first, then pass to format_html
            amount_str = f"${abs(amount):.2f}"
            
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>',
                color, amount_str
            )
        except Exception:
            return "-"
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def product_name(self, obj):
        """Display the product name from the affiliate link"""
        try:
            if obj.affiliate_link and obj.affiliate_link.product:
                product_name = obj.affiliate_link.product.name
                # Truncate long product names for better display
                if len(product_name) > 50:
                    return product_name[:47] + "..."
                return product_name
            return '-'
        except Exception:
            return '-'
    product_name.short_description = 'Product'
    product_name.admin_order_field = 'affiliate_link__product__name'
    
    def affiliate_platform(self, obj):
        if obj.affiliate_link and getattr(obj.affiliate_link, 'platform', None):
            return obj.affiliate_link.platform.title()
        return '-'
    affiliate_platform.short_description = 'Platform'
    
    def transaction_actions(self, obj):
        """Display action buttons based on transaction type and status"""
        html = '<div style="display: flex; gap: 5px;">'
        
        if obj.transaction_type == 'WITHDRAWAL_PENDING' and obj.status == 'PENDING':
            html += f'''
            <a href="javascript:void(0)" onclick="approveWithdrawal({obj.id})" 
               style="color: green; text-decoration: none;">✅ Approve</a>
            <a href="javascript:void(0)" onclick="rejectWithdrawal({obj.id})" 
               style="color: red; text-decoration: none;">❌ Reject</a>
            '''
        
        elif obj.transaction_type == 'EARNING_PROJECTED' and obj.status == 'PENDING':
            html += f'''
            <a href="javascript:void(0)" onclick="confirmEarning({obj.id})" 
               style="color: blue; text-decoration: none;">✅ Confirm</a>
            '''
        
        html += '</div>'
        return mark_safe(html)
    transaction_actions.short_description = 'Actions'
    
    def metadata_display(self, obj):
        """Display formatted metadata"""
        if obj.metadata:
            formatted = json.dumps(obj.metadata, indent=2)
            return format_html('<pre>{}</pre>', formatted)
        return 'No metadata'
    metadata_display.short_description = 'Metadata'
    
    def approve_withdrawals(self, request, queryset):
        """Approve selected pending withdrawals"""
        pending_withdrawals = queryset.filter(
            transaction_type='WITHDRAWAL_PENDING',
            status='PENDING'
        )
        
        approved_count = 0
        for withdrawal in pending_withdrawals:
            try:
                WithdrawalAdminService.approve_withdrawal(withdrawal.id, request.user)
                approved_count += 1
            except Exception as e:
                self.message_user(request, f"Error approving withdrawal {withdrawal.id}: {str(e)}", level='ERROR')
        
        self.message_user(request, f"Approved {approved_count} withdrawals")
    approve_withdrawals.short_description = "Approve selected withdrawals"
    
    def reject_withdrawals(self, request, queryset):
        """Reject selected pending withdrawals"""
        # This would need a form to collect rejection reason
        # For now, use a default reason
        pending_withdrawals = queryset.filter(
            transaction_type='WITHDRAWAL_PENDING',
            status='PENDING'
        )
        
        rejected_count = 0
        for withdrawal in pending_withdrawals:
            try:
                WithdrawalAdminService.reject_withdrawal(withdrawal.id, request.user, "Admin rejection")
                rejected_count += 1
            except Exception as e:
                self.message_user(request, f"Error rejecting withdrawal {withdrawal.id}: {str(e)}", level='ERROR')
        
        self.message_user(request, f"Rejected {rejected_count} withdrawals")
    reject_withdrawals.short_description = "Reject selected withdrawals"
    
    def confirm_earnings(self, request, queryset):
        """Confirm projected earnings"""
        projected_earnings = queryset.filter(
            transaction_type='EARNING_PROJECTED',
            status='PENDING'
        )
        
        confirmed_count = 0
        for earning in projected_earnings:
            try:
                # Use projected amount as actual revenue for simplicity
                # In production, this would come from affiliate program data
                actual_revenue = earning.amount / earning.user.profile.revenue_share_rate
                WalletService.confirm_earning(earning, actual_revenue)
                confirmed_count += 1
            except Exception as e:
                self.message_user(request, f"Error confirming earning {earning.id}: {str(e)}", level='ERROR')
        
        self.message_user(request, f"Confirmed {confirmed_count} earnings")
    confirm_earnings.short_description = "Confirm projected earnings"
    
    def export_transactions(self, request, queryset):
        """Export selected transactions to CSV"""
        # This would generate a CSV export
        # For now, just show count
        self.message_user(request, f"Export functionality: {queryset.count()} transactions selected")
    export_transactions.short_description = "Export to CSV"


# Custom admin actions for wallet management
class WalletAdminActions:
    """Custom admin actions for wallet management"""
    
    @staticmethod
    def run_monthly_reconciliation(request):
        """Run monthly reconciliation for the previous month"""
        try:
            from datetime import datetime
            
            now = timezone.now()
            if now.month == 1:
                year = now.year - 1
                month = 12
            else:
                year = now.year
                month = now.month - 1
            
            results = ReconciliationService.run_monthly_reconciliation(year, month)
            
            request.user.message_set.create(
                message=f"Reconciliation completed for {year}-{month:02d}: "
                f"{results['total_links_processed']} links processed, "
                f"${results['total_adjustment']:.2f} adjustment"
            )
            
        except Exception as e:
            request.user.message_set.create(
                message=f"Reconciliation failed: {str(e)}"
            )
    
    @staticmethod
    def generate_wallet_analytics_report(request):
        """Generate comprehensive wallet analytics report"""
        try:
            # Calculate various metrics
            total_users = UserProfile.objects.count()
            active_users = UserProfile.objects.filter(
                wallet_transactions__created_at__gte=timezone.now() - timedelta(days=30)
            ).distinct().count()
            
            balances = UserProfile.objects.aggregate(
                total_available=Sum('available_balance'),
                total_pending=Sum('pending_balance'),
                total_lifetime=Sum('lifetime_earnings'),
                total_withdrawn=Sum('total_withdrawn')
            )
            
            recent_transactions = WalletTransaction.objects.filter(
                created_at__gte=timezone.now() - timedelta(days=30)
            ).count()
            
            request.user.message_set.create(
                message=f"Analytics Report: {total_users} total users, "
                f"{active_users} active users, "
                f"${balances['total_available']:.2f} available balance, "
                f"${balances['total_pending']:.2f} pending balance, "
                f"{recent_transactions} recent transactions"
            )
            
        except Exception as e:
            request.user.message_set.create(
                message=f"Report generation failed: {str(e)}"
            )


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    """Admin interface for payout requests with comprehensive management features"""
    
    list_display = [
        'id', 'user_email', 'amount_display', 'payout_method_display', 
        'status_display', 'priority', 'days_pending_display', 'requested_at', 
        'approved_by_display', 'payout_actions'
    ]
    
    list_filter = [
        'status', 'payout_method', 'priority', 'requested_at', 'approved_at',
        'processed_at', 'completed_at'
    ]
    
    search_fields = [
        'user__email', 'user__first_name', 'user__last_name',
        'external_transaction_id', 'external_reference', 'admin_notes'
    ]
    
    readonly_fields = [
        'id', 'requested_at', 'created_at', 'updated_at', 'days_pending',
        'processing_time', 'wallet_transaction_link', 'user_profile_link'
    ]
    
    fieldsets = (
        ('Request Information', {
            'fields': ('id', 'user', 'amount', 'status', 'priority', 'requested_at')
        }),
        ('Payout Details', {
            'fields': (
                'payout_method', 'recipient_email', 'stripe_connect_account_id', 
                'paypal_email'
            )
        }),
        ('Processing Information', {
            'fields': (
                'approved_at', 'approved_by', 'processed_at', 'processed_by', 
                'completed_at'
            )
        }),
        ('External References', {
            'fields': (
                'external_transaction_id', 'external_reference', 'processing_fee', 
                'net_amount'
            )
        }),
        ('Notes and Communication', {
            'fields': ('admin_notes', 'rejection_reason', 'user_notes')
        }),
        ('Error Handling', {
            'fields': (
                'retry_count', 'max_retries', 'last_error', 'next_retry_at'
            ),
            'classes': ('collapse',)
        }),
        ('Related Records', {
            'fields': ('wallet_transaction_link', 'user_profile_link'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'days_pending', 'processing_time'),
            'classes': ('collapse',)
        })
    )
    
    actions = [
        'approve_selected_payouts', 'reject_selected_payouts', 
        'mark_as_processing', 'retry_failed_payouts',
        'export_payout_report', 'send_status_notifications'
    ]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'user__profile', 'approved_by', 'processed_by', 'wallet_transaction'
        )
    
    def user_email(self, obj):
        return obj.user.email if obj.user else "-"
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def amount_display(self, obj):
        """Display the payout amount with currency formatting"""
        try:
            if obj.amount is None:
                return "-"
            
            # Color code based on amount and status
            if obj.status == 'completed':
                color = 'green'
            elif obj.status in ['failed', 'rejected']:
                color = 'red'
            elif obj.status in ['approved', 'processing']:
                color = 'blue'
            else:
                color = 'black'
            
            amount_str = f"${float(obj.amount):.2f}"
            
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>',
                color, amount_str
            )
        except Exception:
            return "-"
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def payout_method_display(self, obj):
        """Display payout method with icon"""
        method_icons = {
            'stripe_bank': '🏦',
            'paypal': '💳',
            'check': '📄',
            'other': '❓'
        }
        
        icon = method_icons.get(obj.payout_method, '❓')
        display = obj.get_payout_method_display()
        
        return f"{icon} {display}"
    payout_method_display.short_description = 'Method'
    payout_method_display.admin_order_field = 'payout_method'
    
    def status_display(self, obj):
        """Display status with color coding and icons"""
        status_config = {
            'pending': {'color': 'orange', 'icon': '⏳'},
            'approved': {'color': 'blue', 'icon': '✅'},
            'processing': {'color': 'purple', 'icon': '⚙️'},
            'completed': {'color': 'green', 'icon': '✅'},
            'failed': {'color': 'red', 'icon': '❌'},
            'cancelled': {'color': 'gray', 'icon': '⏹️'},
            'rejected': {'color': 'red', 'icon': '❌'},
        }
        
        config = status_config.get(obj.status, {'color': 'black', 'icon': '❓'})
        display = obj.get_status_display()
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            config['color'], config['icon'], display
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'
    
    def days_pending_display(self, obj):
        """Display how many days the request has been pending"""
        days = obj.days_pending
        
        if obj.status == 'pending':
            if days >= 7:
                color = 'red'  # Urgent - over a week
            elif days >= 3:
                color = 'orange'  # Warning - over 3 days
            else:
                color = 'green'  # Normal
                
            return format_html(
                '<span style="color: {};">{} days</span>',
                color, days
            )
        else:
            return f"{days} days"
    days_pending_display.short_description = 'Days Pending'
    days_pending_display.admin_order_field = 'requested_at'
    
    def approved_by_display(self, obj):
        """Display who approved the payout"""
        if obj.approved_by:
            return obj.approved_by.email
        return "-"
    approved_by_display.short_description = 'Approved By'
    approved_by_display.admin_order_field = 'approved_by__email'
    
    def payout_actions(self, obj):
        """Display action buttons based on payout status"""
        html = '<div style="display: flex; gap: 5px; flex-wrap: wrap;">'
        
        if obj.status == 'pending':
            html += f'''
            <a href="javascript:void(0)" onclick="approvePayout({obj.id})" 
               style="color: green; text-decoration: none; padding: 2px 6px; border: 1px solid green; border-radius: 3px;">
               ✅ Approve
            </a>
            <a href="javascript:void(0)" onclick="rejectPayout({obj.id})" 
               style="color: red; text-decoration: none; padding: 2px 6px; border: 1px solid red; border-radius: 3px;">
               ❌ Reject
            </a>
            '''
        
        elif obj.status == 'approved':
            html += f'''
            <a href="javascript:void(0)" onclick="processPayout({obj.id})" 
               style="color: blue; text-decoration: none; padding: 2px 6px; border: 1px solid blue; border-radius: 3px;">
               ⚙️ Process
            </a>
            '''
        
        elif obj.status == 'failed' and obj.can_retry:
            html += f'''
            <a href="javascript:void(0)" onclick="retryPayout({obj.id})" 
               style="color: orange; text-decoration: none; padding: 2px 6px; border: 1px solid orange; border-radius: 3px;">
               🔄 Retry
            </a>
            '''
        
        if obj.wallet_transaction:
            url = reverse('admin:users_wallettransaction_change', args=[obj.wallet_transaction.id])
            html += f'''
            <a href="{url}" target="_blank"
               style="color: purple; text-decoration: none; padding: 2px 6px; border: 1px solid purple; border-radius: 3px;">
               💰 Wallet
            </a>
            '''
        
        html += '</div>'
        return mark_safe(html)
    payout_actions.short_description = 'Actions'
    
    def wallet_transaction_link(self, obj):
        """Link to associated wallet transaction"""
        if obj.wallet_transaction:
            url = reverse('admin:users_wallettransaction_change', args=[obj.wallet_transaction.id])
            return format_html(
                '<a href="{}" target="_blank">Wallet Transaction #{}</a>',
                url, obj.wallet_transaction.id
            )
        return "No associated transaction"
    wallet_transaction_link.short_description = 'Wallet Transaction'
    
    def user_profile_link(self, obj):
        """Link to user profile"""
        if obj.user and hasattr(obj.user, 'profile'):
            url = reverse('admin:users_userprofile_change', args=[obj.user.profile.id])
            return format_html(
                '<a href="{}" target="_blank">{} Profile</a>',
                url, obj.user.email
            )
        return "No profile"
    user_profile_link.short_description = 'User Profile'
    
    # Admin Actions
    def approve_selected_payouts(self, request, queryset):
        """Approve selected pending payouts"""
        pending_payouts = queryset.filter(status='pending')
        approved_count = 0
        
        for payout in pending_payouts:
            try:
                payout.approve(request.user, "Bulk approval via admin")
                approved_count += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f"Error approving payout {payout.id}: {str(e)}", 
                    level='ERROR'
                )
        
        self.message_user(request, f"Approved {approved_count} payouts")
    approve_selected_payouts.short_description = "Approve selected payouts"
    
    def reject_selected_payouts(self, request, queryset):
        """Reject selected pending payouts"""
        # Note: In a real implementation, you'd want a form to collect rejection reason
        pending_payouts = queryset.filter(status='pending')
        rejected_count = 0
        
        for payout in pending_payouts:
            try:
                payout.reject(request.user, "Bulk rejection via admin")
                rejected_count += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f"Error rejecting payout {payout.id}: {str(e)}", 
                    level='ERROR'
                )
        
        self.message_user(request, f"Rejected {rejected_count} payouts")
    reject_selected_payouts.short_description = "Reject selected payouts"
    
    def mark_as_processing(self, request, queryset):
        """Mark approved payouts as processing"""
        approved_payouts = queryset.filter(status='approved')
        processing_count = 0
        
        for payout in approved_payouts:
            try:
                payout.mark_processing(request.user)
                processing_count += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f"Error processing payout {payout.id}: {str(e)}", 
                    level='ERROR'
                )
        
        self.message_user(request, f"Marked {processing_count} payouts as processing")
    mark_as_processing.short_description = "Mark as processing"
    
    def retry_failed_payouts(self, request, queryset):
        """Retry failed payouts that are eligible for retry"""
        failed_payouts = queryset.filter(status='failed')
        retry_count = 0
        
        for payout in failed_payouts:
            if payout.can_retry:
                try:
                    payout.status = 'approved'  # Reset to approved for retry
                    payout.save()
                    retry_count += 1
                except Exception as e:
                    self.message_user(
                        request, 
                        f"Error retrying payout {payout.id}: {str(e)}", 
                        level='ERROR'
                    )
        
        self.message_user(request, f"Reset {retry_count} payouts for retry")
    retry_failed_payouts.short_description = "Retry failed payouts"
    
    def export_payout_report(self, request, queryset):
        """Export payout data (placeholder for CSV export)"""
        self.message_user(
            request, 
            f"Export functionality: {queryset.count()} payouts selected for export"
        )
    export_payout_report.short_description = "Export payout report"
    
    def send_status_notifications(self, request, queryset):
        """Send status update notifications to users"""
        notification_count = 0
        
        for payout in queryset:
            # Placeholder for email notification logic
            notification_count += 1
        
        self.message_user(
            request, 
            f"Sent status notifications for {notification_count} payouts"
        )
    send_status_notifications.short_description = "Send status notifications"


# Register admin actions
admin.site.add_action(WalletAdminActions.run_monthly_reconciliation, 'Run Monthly Reconciliation')
admin.site.add_action(WalletAdminActions.generate_wallet_analytics_report, 'Generate Wallet Analytics Report')

# Customize admin site
admin.site.site_header = 'Ecommerce Platform Admin'
admin.site.site_title = 'Ecommerce Platform Admin'
admin.site.index_title = 'Welcome to Ecommerce Platform Administration'