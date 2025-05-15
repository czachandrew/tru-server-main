from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json
import redis
import logging
from affiliates.models import AffiliateLink
from django.utils import timezone
from products.models import Product, Manufacturer, Category
from django.utils.text import slugify
import traceback

logger = logging.getLogger('affiliate_tasks')

# Create your views here.

@csrf_exempt
def affiliate_callback(request, task_id):
    """Handle callback from puppeteer worker with affiliate link results"""
    if request.method != 'POST':
        return HttpResponse("POST method required", status=405)
    
    logger.info(f"Received callback for task_id: {task_id}")
    
    try:
        # Get the data from the request
        data = json.loads(request.body)
        affiliate_url = data.get('affiliateUrl')
        error = data.get('error')
        
        # Get Redis connection with proper fallbacks
        redis_kwargs = {
            'host': getattr(settings, 'REDIS_HOST', 'localhost'),
            'port': getattr(settings, 'REDIS_PORT', 6379),
            'decode_responses': True
        }
        
        # Only add password if it exists in settings
        if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
            redis_kwargs['password'] = settings.REDIS_PASSWORD
            
        r = redis.Redis(**redis_kwargs)
        
        # Get the affiliate_link_id from Redis
        affiliate_link_id = r.get(f"pending_affiliate_task:{task_id}")
        if not affiliate_link_id:
            logger.error(f"No pending task found for task_id: {task_id}")
            return HttpResponse("Task not found", status=404)
        
        # Update the affiliate link
        affiliate_link = AffiliateLink.objects.get(pk=affiliate_link_id)
        
        if error:
            affiliate_link.affiliate_url = f"ERROR: {error}"
            logger.error(f"Error generating affiliate URL for task {task_id}: {error}")
        else:
            affiliate_link.affiliate_url = affiliate_url
            logger.info(f"Successfully updated affiliate URL for task {task_id}")
        
        affiliate_link.save()
        
        # Clean up Redis
        r.delete(f"pending_affiliate_task:{task_id}")
        
        # Store the result in Redis with the task_id for clients to poll
        result_data = {
            "affiliate_link_id": affiliate_link.id,
            "status": "error" if error else "success",
            "affiliate_url": affiliate_url if not error else None,
            "error": error if error else None,
            "timestamp": timezone.now().isoformat()
        }
        # Store this for 1 hour (clients should poll more frequently)
        r.set(f"affiliate_task_status:{task_id}", json.dumps(result_data), ex=3600)
        
        return HttpResponse("Success", status=200)
    except Exception as e:
        logger.error(f"Error processing callback: {str(e)}", exc_info=True)
        return HttpResponse(f"Error: {str(e)}", status=500)

def check_affiliate_status(request):
    # Get the task IDs the extension is waiting for
    task_ids = request.GET.get('task_ids', '').split(',')
    results = {}
    
    if task_ids and task_ids[0]:  # Check if we have any valid task IDs
        # Get Redis connection
        redis_kwargs = {
            'host': getattr(settings, 'REDIS_HOST', 'localhost'),
            'port': getattr(settings, 'REDIS_PORT', 6379),
            'decode_responses': True
        }
        if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
            redis_kwargs['password'] = settings.REDIS_PASSWORD
        r = redis.Redis(**redis_kwargs)
        
        for task_id in task_ids:
            # Check if this task has completed
            # We now store task status in Redis when completed
            task_status = r.get(f"affiliate_task_status:{task_id}")
            if task_status:
                # Parse the stored result
                try:
                    results[task_id] = json.loads(task_status)
                    # Task has been delivered to client, can clean up
                    r.delete(f"affiliate_task_status:{task_id}")
                except:
                    results[task_id] = {"error": "Invalid result format"}
    
    return JsonResponse({"results": results})

@csrf_exempt
def standalone_callback(request, task_id):
    """Handle callback from puppeteer worker with standalone affiliate link results"""
    if request.method != 'POST':
        return HttpResponse("POST method required", status=405)
    
    logger.info(f"Received standalone callback for task_id: {task_id}")
    
    try:
        # Get the data from the request
        data = json.loads(request.body)
        print(f"CALLBACK DATA RECEIVED: {json.dumps(data, indent=2)}")
        
        affiliate_url = data.get('affiliateUrl')
        error = data.get('error')
        
        if error:
            logger.error(f"Error from puppeteer worker: {error}")
            store_result_in_redis(task_id, error=error)
            return HttpResponse("Error recorded", status=200)
            
        # Get Redis connection
        redis_kwargs = get_redis_kwargs()
        r = redis.Redis(**redis_kwargs)
        
        # Get the ASIN and original URL from Redis
        asin = r.get(f"pending_standalone_task:{task_id}")
        original_url = r.get(f"pending_standalone_original_url:{task_id}")
        
        if not asin:
            logger.error(f"No pending standalone task found for task_id: {task_id}")
            return HttpResponse("Task not found", status=404)
            
        # Get product data from Redis
        product_data_json = r.get(f"pending_product_data:{task_id}")
        print(f"Product data from Redis: {product_data_json}")
        
        if product_data_json:
            # Parse product data from Redis
            product_data = json.loads(product_data_json)
            
            # Create manufacturer
            manufacturer_name = product_data.get('manufacturer', 'Amazon Marketplace')
            manufacturer, _ = Manufacturer.objects.get_or_create(
                name=manufacturer_name,
                defaults={'slug': slugify(manufacturer_name)}
            )
            
            # Create product using data from Chrome extension
            product = Product.objects.create(
                name=product_data.get('name', f"Amazon Product {asin}"),
                slug=slugify(product_data.get('name', f"amazon-product-{asin}")),
                description=product_data.get('description', ''),
                part_number=product_data.get('partNumber') or asin,
                manufacturer=manufacturer,
                main_image=product_data.get('mainImage', ''),
                status='active',
                source='amazon'
            )
            
            # Save technical details if available
            if 'technicalDetails' in product_data:
                product.specifications = product_data['technicalDetails']
                product.save()
                
            print(f"Created product: {product.id} - {product.name}")
        else:
            # Fallback to simple product creation
            manufacturer, _ = Manufacturer.objects.get_or_create(
                name="Amazon Marketplace",
                defaults={'slug': 'amazon-marketplace'}
            )
            
            product = Product.objects.create(
                name=f"Amazon Product {asin}",
                slug=f"amazon-product-{asin}",
                part_number=asin,
                manufacturer=manufacturer,
                status='active',
                source='amazon'
            )
            print(f"Created product (fallback): {product.id}")
            
        # Create affiliate link
        affiliate_link = AffiliateLink.objects.create(
            product=product,
            platform='amazon',
            platform_id=asin,
            original_url=original_url,
            affiliate_url=affiliate_url,
            is_active=True
        )
        
        # Store result in Redis
        result_data = {
            "status": "success",
            "affiliate_url": affiliate_url,
            "original_url": original_url,
            "asin": asin,
            "product_id": product.id,
            "product_name": product.name,
            "affiliate_link_id": affiliate_link.id,
            "timestamp": timezone.now().isoformat()
        }
        
        # Store for 24 hours
        r.set(f"standalone_task_status:{task_id}", json.dumps(result_data), ex=86400)
        
        # Clean up Redis task markers
        r.delete(f"pending_standalone_task:{task_id}")
        r.delete(f"pending_standalone_original_url:{task_id}")
        r.delete(f"pending_product_data:{task_id}")
        
        # Publish notification
        r.publish("affiliate_notifications", json.dumps({
            "type": "product_created",
            "task_id": task_id,
            "asin": asin,
            "product_id": product.id,
            "timestamp": timezone.now().isoformat()
        }))
        
        print(f"Successfully processed affiliate callback for task {task_id}")
        return HttpResponse("Success", status=200)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        traceback.print_exc()
        return HttpResponse(f"Error: {str(e)}", status=500)

def get_redis_kwargs():
    """Helper to get standardized Redis connection kwargs"""
    redis_kwargs = {
        'host': getattr(settings, 'REDIS_HOST', 'localhost'),
        'port': getattr(settings, 'REDIS_PORT', 6379),
        'decode_responses': True
    }
    
    # Only add password if it exists in settings
    if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
        redis_kwargs['password'] = settings.REDIS_PASSWORD
        
    return redis_kwargs

def store_result_in_redis(task_id, error=None):
    """Helper to store task results in Redis"""
    redis_kwargs = get_redis_kwargs()
    r = redis.Redis(**redis_kwargs)
    
    # Get the ASIN and original URL
    asin = r.get(f"pending_standalone_task:{task_id}")
    original_url = r.get(f"pending_standalone_original_url:{task_id}")
    
    # Store the result
    result_data = {
        "status": "error" if error else "success",
        "affiliate_url": None if error else None,
        "original_url": original_url,
        "asin": asin,
        "error": error if error else None,
        "timestamp": timezone.now().isoformat()
    }
    
    # Store for 24 hours
    r.set(f"standalone_task_status:{task_id}", json.dumps(result_data), ex=86400)
    
    # Clean up
    r.delete(f"pending_standalone_task:{task_id}")
    r.delete(f"pending_standalone_original_url:{task_id}")
