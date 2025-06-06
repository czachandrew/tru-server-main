"""ecommerce_platform URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from ecommerce_platform.graphql.views import DebugGraphQLView
from ecommerce_platform.views import test_auth, debug_token, test_simple_task, check_task_status
from affiliates.views import affiliate_callback, standalone_callback, check_affiliate_task_status
from products.views import toggle_demo_mode, demo_status
from graphene_django.views import GraphQLView
import json
import traceback
from django.http import JsonResponse

class SimpleDebugGraphQLView(GraphQLView):
    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        print("\n" + "="*80)
        print(f"GRAPHQL REQUEST: {request.method} {request.path}")
        print("-"*80)
        
        # Print headers (excluding sensitive ones)
        headers = {k: v for k, v in request.headers.items() 
                  if k.lower() not in ('cookie', 'authorization')}
        print(f"HEADERS: {json.dumps(headers, indent=2)}")
        
        # Print request body for POST requests
        if request.method == 'POST':
            try:
                raw_body = request.body.decode('utf-8')
                print(f"RAW BODY: {raw_body}")
                
                try:
                    body_json = json.loads(raw_body)
                    print(f"PARSED JSON: {json.dumps(body_json, indent=2)}")
                    
                    # Print variables separately for clarity
                    if 'variables' in body_json and body_json['variables']:
                        print(f"VARIABLES: {json.dumps(body_json['variables'], indent=2)}")
                except json.JSONDecodeError as e:
                    print(f"INVALID JSON: {str(e)}")
                    return JsonResponse({
                        "errors": [{
                            "message": f"Invalid JSON: {str(e)}",
                            "extensions": {"code": "INVALID_JSON"}
                        }]
                    }, status=400)
            except Exception as e:
                print(f"ERROR PROCESSING REQUEST: {str(e)}")
                traceback.print_exc()
        
        try:
            # Let the parent class handle the request normally
            response = super().dispatch(request, *args, **kwargs)
            
            # Check for authentication errors in GraphQL response
            if response.status_code == 200 and hasattr(response, 'content'):
                try:
                    content = json.loads(response.content)
                    if 'errors' in content:
                        for error in content['errors']:
                            extensions = error.get('extensions', {})
                            error_code = extensions.get('code')
                            
                            # Return proper HTTP status for auth errors
                            if error_code in ['INVALID_CREDENTIALS', 'EMAIL_NOT_VERIFIED', 'AUTHENTICATION_FAILED']:
                                response.status_code = 401
                            elif error_code in ['PERMISSION_DENIED']:
                                response.status_code = 403
                            elif error_code in ['INVALID_INPUT', 'VALIDATION_ERROR']:
                                response.status_code = 400
                except:
                    pass  # If we can't parse, keep original response
            
            print(f"RESPONSE STATUS: {response.status_code}")
            
            # Print error responses
            if response.status_code >= 400:
                try:
                    content = json.loads(response.content)
                    print(f"ERROR RESPONSE: {json.dumps(content, indent=2)}")
                except Exception as e:
                    print(f"ERROR PARSING RESPONSE: {str(e)}")
            
            print("="*80 + "\n")
            return response
            
        except Exception as e:
            print(f"UNHANDLED EXCEPTION: {str(e)}")
            traceback.print_exc()
            print("="*80 + "\n")
            
            # Return 500 for server errors
            return JsonResponse({
                "errors": [{
                    "message": str(e),
                    "extensions": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "traceback": traceback.format_exc()
                    }
                }]
            }, status=500)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('graphql/', csrf_exempt(SimpleDebugGraphQLView.as_view(graphiql=True))),
    path('test-auth/', test_auth, name='test-auth'),
    path('debug-token/', debug_token, name='debug-token'),
    path('api/affiliate/callback/<str:task_id>/', affiliate_callback, name='affiliate_callback'),
    path('api/affiliate/standalone/<str:task_id>/', standalone_callback, name='standalone_callback'),
    path('api/affiliate/status/', check_affiliate_task_status, name='check_affiliate_status'),
    path('test-task/', test_simple_task, name='test-task'),
    path('check-task/<str:task_id>/', check_task_status, name='check-task'),
    path('products/toggle-demo-mode/', toggle_demo_mode, name='toggle_demo_mode'),
    path('products/demo-status/', demo_status, name='demo_status'),
]