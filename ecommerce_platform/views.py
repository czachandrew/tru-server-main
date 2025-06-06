from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import jwt
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import json

@require_http_methods(["GET"])
def test_auth(request):
    """Simple view to test if authentication is working"""
    if request.user.is_authenticated:
        return JsonResponse({
            "authenticated": True,
            "user_id": request.user.id,
            "email": request.user.email,
        })
    return JsonResponse({"authenticated": False})

@csrf_exempt
def debug_token(request):
    """Debug endpoint to manually verify tokens"""
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST method allowed"})
    
    try:
        data = json.loads(request.body)
        token = data.get('token')
        
        if not token:
            return JsonResponse({"error": "No token provided"})
        
        # Try without verification
        unverified = jwt.decode(
            token, 
            options={"verify_signature": False},
            algorithms=['HS256']
        )
        
        # Try with verification
        try:
            verified = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=['HS256']
            )
            verified_success = True
        except Exception as e:
            verified_success = False
            verified = str(e)
        
        return JsonResponse({
            "unverified_payload": unverified,
            "verification_success": verified_success,
            "verified_result": verified,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)})

def test_simple_task(request):
    """Test if Django Q task queuing is working"""
    try:
        from django_q.tasks import async_task
        import time
        
        # Queue a simple test task
        task_id = async_task('time.sleep', 1)
        
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'message': 'Test task queued successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

def check_task_status(request, task_id):
    """Check the status of a specific task"""
    try:
        from django_q.models import Task
        
        task = Task.objects.get(id=task_id)
        
        return JsonResponse({
            'task_id': task_id,
            'function': task.func,
            'started': task.started,
            'stopped': task.stopped,
            'success': task.success,
            'result': str(task.result) if task.result else None
        })
        
    except Task.DoesNotExist:
        return JsonResponse({
            'error': 'Task not found'
        }, status=404)
