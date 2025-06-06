from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import Product

# Create your views here.

@csrf_exempt
@require_http_methods(["POST"])
def toggle_demo_mode(request):
    """API endpoint to enable/disable demo products"""
    try:
        data = json.loads(request.body)
        action = data.get('action')  # 'enable' or 'disable'
        
        if action == 'enable':
            # Run the management command programmatically
            from django.core.management import call_command
            from io import StringIO
            
            out = StringIO()
            call_command('create_demo_products', '--clear-existing', stdout=out)
            
            return JsonResponse({
                'success': True,
                'message': 'Demo products created successfully',
                'output': out.getvalue()
            })
            
        elif action == 'disable':
            deleted_count = Product.objects.filter(is_demo=True).count()
            Product.objects.filter(is_demo=True).delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Deleted {deleted_count} demo products',
                'deleted_count': deleted_count
            })
            
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid action. Use "enable" or "disable"'
            }, status=400)
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
def demo_status(request):
    """Get current demo product status"""
    demo_count = Product.objects.filter(is_demo=True).count()
    total_count = Product.objects.count()
    
    return JsonResponse({
        'demo_products_count': demo_count,
        'total_products_count': total_count,
        'demo_enabled': demo_count > 0
    })
