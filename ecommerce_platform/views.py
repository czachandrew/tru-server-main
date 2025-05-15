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
