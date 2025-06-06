from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json
import redis
import logging
import uuid
import re  # Add regex import for part number extraction
from affiliates.models import AffiliateLink
from django.utils import timezone
from products.models import Product, Manufacturer, Category
from django.utils.text import slugify
import traceback
import os
from urllib.parse import urlparse

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
        
        # Get Redis connection
        redis_kwargs = get_redis_connection()
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

def get_redis_connection():
    if 'REDISCLOUD_URL' in os.environ:
        url = urlparse(os.environ['REDISCLOUD_URL'])
        return {
            'host': url.hostname,
            'port': url.port,
            'password': url.password,
            'decode_responses': True
        }
    else:
        redis_kwargs = {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', 6379)),
            'decode_responses': True
        }
        if os.getenv('REDIS_PASSWORD'):
            redis_kwargs['password'] = os.getenv('REDIS_PASSWORD')
        return redis_kwargs

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
        redis_kwargs = get_redis_connection()
        r = redis.Redis(**redis_kwargs)
        
        # Check if we already processed this task
        existing_result = r.get(f"standalone_task_status:{task_id}")
        if existing_result:
            logger.info(f"Task {task_id} already processed, returning success")
            return HttpResponse("Already processed", status=200)
        
        # Get the ASIN and original URL from Redis
        asin = r.get(f"pending_standalone_task:{task_id}")
        original_url = r.get(f"pending_standalone_original_url:{task_id}")
        
        if not asin:
            logger.error(f"No pending standalone task found for task_id: {task_id}")
            
            # Check if affiliate link already exists for this ASIN (task might be duplicate)
            if affiliate_url:
                # Try to extract ASIN from affiliate URL
                import re
                asin_match = re.search(r'/dp/([A-Z0-9]{10})', affiliate_url)
                if asin_match:
                    extracted_asin = asin_match.group(1)
                    logger.info(f"Extracted ASIN {extracted_asin} from affiliate URL, checking for existing link")
                    
                    # Check if we already have this affiliate link
                    existing_link = AffiliateLink.objects.filter(
                        platform='amazon',
                        platform_id=extracted_asin,
                        affiliate_url=affiliate_url
                    ).first()
                    
                    if existing_link:
                        logger.info(f"Affiliate link already exists: {existing_link.id}")
                        return HttpResponse("Link already exists", status=200)
            
            return HttpResponse("Task not found", status=404)
        
        # Use affiliate_url as original_url if original_url is not present
        if not original_url:
            logger.warning(f"No original URL found for task_id: {task_id}, using affiliate_url as original_url")
            original_url = affiliate_url
        
        # Get product data from Redis
        product_data_json = r.get(f"pending_product_data:{task_id}")
        print(f"Product data from Redis: {product_data_json}")
        
        product = None
        
        if product_data_json:
            # Parse product data from Redis
            product_data = json.loads(product_data_json)
            
            # Create manufacturer
            manufacturer_name = product_data.get('manufacturer', 'Amazon Marketplace')
            try:
                # First try to find by exact name
                manufacturer = Manufacturer.objects.get(name__iexact=manufacturer_name)
            except Manufacturer.DoesNotExist:
                # Create with unique slug
                base_slug = slugify(manufacturer_name)
                unique_slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                
                manufacturer = Manufacturer.objects.create(
                    name=manufacturer_name,
                    slug=unique_slug
                )
            
            # Extract real part number
            extracted_part_number = extract_real_part_number(product_data, asin)
            
            # Check if product already exists by manufacturer + part_number
            try:
                product = Product.objects.get(
                    manufacturer=manufacturer,
                    part_number=extracted_part_number
                )
                print(f"Found existing product: {product.id} - {product.name}")
            except Product.DoesNotExist:
                # Product doesn't exist, create it
                try:
                    product = Product.objects.create(
                        name=product_data.get('name', f"Amazon Product {asin}"),
                        slug=slugify(product_data.get('name', f"amazon-product-{asin}")),
                        description=product_data.get('description', ''),
                        part_number=extracted_part_number,
                        manufacturer=manufacturer,
                        main_image=product_data.get('mainImage', ''),
                        status='active',
                        source='amazon'
                    )
                    
                    # Save technical details if available
                    if 'technicalDetails' in product_data:
                        product.specifications = product_data['technicalDetails']
                        product.save()
                        
                    print(f"Created new product: {product.id} - {product.name}")
                except Exception as create_error:
                    print(f"Error creating product: {create_error}")
                    # Try to find existing product by ASIN as fallback
                    existing_by_asin = Product.objects.filter(
                        part_number=asin,
                        source='amazon'
                    ).first()
                    if existing_by_asin:
                        product = existing_by_asin
                        print(f"Found fallback product by ASIN: {product.id}")
                    else:
                        raise create_error
                
        else:
            # Fallback to simple product creation
            manufacturer, _ = Manufacturer.objects.get_or_create(
                name="Amazon Marketplace",
                defaults={'slug': 'amazon-marketplace'}
            )
            
            # Check if product already exists by ASIN
            try:
                product = Product.objects.get(
                    manufacturer=manufacturer,
                    part_number=asin
                )
                print(f"Found existing fallback product: {product.id} - {product.name}")
            except Product.DoesNotExist:
                # Create new product
                try:
                    product = Product.objects.create(
                        name=f"Amazon Product {asin}",
                        slug=f"amazon-product-{asin}",
                        part_number=asin,
                        manufacturer=manufacturer,
                        status='active',
                        source='amazon'
                    )
                    print(f"Created fallback product: {product.id} - Part: {asin}")
                except Exception as fallback_error:
                    print(f"Error creating fallback product: {fallback_error}")
                    raise fallback_error
            
        # Check if affiliate link already exists
        existing_affiliate_link = AffiliateLink.objects.filter(
            product=product,
            platform='amazon',
            platform_id=asin
        ).first()
        
        if existing_affiliate_link:
            # Update existing affiliate link
            existing_affiliate_link.affiliate_url = affiliate_url
            existing_affiliate_link.original_url = original_url
            existing_affiliate_link.is_active = True
            existing_affiliate_link.save()
            affiliate_link = existing_affiliate_link
            print(f"Updated existing affiliate link: {affiliate_link.id}")
        else:
            # Create new affiliate link
            affiliate_link = AffiliateLink.objects.create(
                product=product,
                platform='amazon',
                platform_id=asin,
                original_url=original_url,
                affiliate_url=affiliate_url,
                is_active=True
            )
            print(f"Created new affiliate link: {affiliate_link.id}")
        
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

def store_result_in_redis(task_id, error=None):
    """Helper to store task results in Redis"""
    redis_kwargs = get_redis_connection()
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

@csrf_exempt  # Only if this endpoint doesn't need CSRF protection
def check_affiliate_task_status(request):
    """Endpoint for Chrome extension to check task status"""
    task_id = request.GET.get('task_id')
    
    if not task_id:
        return JsonResponse({"error": "No task_id provided"}, status=400)
    
    # Get Redis connection
    redis_kwargs = get_redis_connection()
    r = redis.Redis(**redis_kwargs)
    
    # Check if task result exists
    task_status_json = r.get(f"standalone_task_status:{task_id}")
    
    if not task_status_json:
        return JsonResponse({
            "status": "pending",
            "message": "Task is still processing"
        })
    
    # Parse and return the result
    task_status = json.loads(task_status_json)
    return JsonResponse(task_status)

def extract_real_part_number(product_data, asin):
    """
    Enhanced extraction of real manufacturer part numbers from Amazon product data
    
    Priority order:
    1. Technical details (multiple field variations)
    2. Enhanced name parsing with brand-specific patterns
    3. Description mining
    4. Fall back to ASIN
    """
    
    print(f"🔍 Extracting part number for ASIN: {asin}")
    
    # Strategy 1: Enhanced technical details extraction
    technical_details_str = product_data.get('technicalDetails')
    if technical_details_str:
        try:
            if isinstance(technical_details_str, str):
                technical_details = json.loads(technical_details_str)
            else:
                technical_details = technical_details_str
            
            print(f"📋 Technical details available: {list(technical_details.keys())[:5]}...")
            
            # Comprehensive list of part number fields
            part_fields = [
                'model name', 'model_name', 'modelname',
                'model number', 'model_number', 'modelnumber', 
                'part number', 'part_number', 'partnumber',
                'sku', 'mpn', 'manufacturer part number',
                'item model number', 'product model',
                'series', 'model', 'item part number'
            ]
            
            for field in part_fields:
                value = technical_details.get(field)
                if value and isinstance(value, str):
                    cleaned = value.strip().upper()
                    # Enhanced validation
                    if (len(cleaned) >= 4 and 
                        cleaned != asin and 
                        not cleaned.startswith('FBA') and
                        not cleaned.startswith('AMAZON') and
                        not cleaned.startswith('B0') and  # Avoid other ASINs
                        re.match(r'^[A-Z0-9\-_]+$', cleaned)):
                        print(f"✅ Found real part number in {field}: {cleaned}")
                        return cleaned
                        
        except (json.JSONDecodeError, TypeError) as e:
            print(f"⚠️ Failed to parse technicalDetails: {e}")
    
    # Strategy 2: Enhanced name parsing with brand-specific patterns
    product_name = product_data.get('name', '')
    if product_name:
        print(f"📝 Analyzing product name: {product_name[:100]}...")
        name_upper = product_name.upper()
        
        # Pattern 1: Model at end of title (Samsung, LG pattern)
        # "SAMSUNG UJ59 Series 32" Computer Monitor VA Panel LU32J590UQNXZA"
        end_pattern = r'\b([A-Z]{2,4}\d{2,}[A-Z0-9]*)\s*$'
        end_match = re.search(end_pattern, name_upper)
        if end_match:
            candidate = end_match.group(1)
            if len(candidate) >= 6:
                print(f"✅ Extracted part number from name (end): {candidate}")
                return candidate
        
        # Pattern 2: Brand-specific model extraction
        brand_patterns = {
            'SAMSUNG': r'SAMSUNG\s+\w*\s*([A-Z]{2}\d{2}[A-Z0-9]*)',
            'LG': r'LG\s+\w*\s*([A-Z0-9\-]{5,})',
            'MSI': r'MSI\s+([A-Z]\d{3,4}[A-Z0-9\-]*)',
            'ASUS': r'ASUS\s+([A-Z0-9\-]{5,})',
            'LOGITECH': r'LOGITECH\s+([A-Z]{2}\d{3,4})',
            'REDRAGON': r'REDRAGON\s+.*?([A-Z]\d{3,4}[A-Z]?)',
        }
        
        for brand, pattern in brand_patterns.items():
            if brand in name_upper:
                match = re.search(pattern, name_upper)
                if match:
                    candidate = match.group(1)
                    if len(candidate) >= 4:
                        print(f"✅ Extracted part number using {brand} pattern: {candidate}")
                        return candidate
        
        # Pattern 3: Generic alphanumeric models (improved)
        # Look for standalone model numbers
        model_pattern = r'\b([A-Z]{1,3}\d{2,}[A-Z0-9\-]*)\b'
        models = re.findall(model_pattern, name_upper)
        if models:
            # Filter out common false positives
            filtered_models = []
            for model in models:
                if (len(model) >= 4 and 
                    not model.startswith('B0') and  # Not ASIN
                    not model in ['USB', 'HDMI', 'RGB', 'LED'] and  # Not tech terms
                    not re.match(r'^\d+$', model)):  # Not just numbers
                    filtered_models.append(model)
            
            if filtered_models:
                # Prefer longer, more specific models
                best_model = max(filtered_models, key=len)
                print(f"✅ Extracted part number from name (pattern): {best_model}")
                return best_model
        
        # Pattern 4: Chipset/generation patterns (for motherboards, etc.)
        chipset_pattern = r'\b([A-Z]\d{3,4}[A-Z]*)\s+(GAMING|PLUS|PRO|WIFI)'
        chipset_match = re.search(chipset_pattern, name_upper)
        if chipset_match:
            base_chipset = chipset_match.group(1)
            modifier = chipset_match.group(2)
            # Build a more complete part number
            candidate = f"{base_chipset}{modifier}"
            print(f"✅ Built part number from chipset pattern: {candidate}")
            return candidate
    
    # Strategy 3: Description mining (if name parsing fails)
    description = product_data.get('description', '')
    if description and len(description) > 50:
        print(f"📄 Mining description for part numbers...")
        desc_upper = description.upper()
        
        # Look for "Model:" or "Part Number:" labels
        labeled_pattern = r'(?:MODEL|PART\s*NUMBER|SKU|MPN):\s*([A-Z0-9\-_]{4,})'
        labeled_match = re.search(labeled_pattern, desc_upper)
        if labeled_match:
            candidate = labeled_match.group(1)
            print(f"✅ Found labeled part number in description: {candidate}")
            return candidate
        
        # Look for standalone alphanumeric codes in description
        desc_models = re.findall(r'\b([A-Z]{2,4}\d{2,}[A-Z0-9\-]*)\b', desc_upper)
        if desc_models:
            # Score by length and uniqueness
            best_desc_model = max(desc_models, key=len)
            if len(best_desc_model) >= 6:
                print(f"✅ Extracted part number from description: {best_desc_model}")
                return best_desc_model
    
    # Strategy 4: Last resort - use ASIN but log it
    print(f"⚠️ No real part number found, falling back to ASIN: {asin}")
    return asin
