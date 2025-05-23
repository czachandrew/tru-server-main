from django_q.tasks import async_task, schedule
from django_q.models import Schedule
from products.models import Product, Manufacturer, Category, ProductCategory
from vendors.models import Vendor
from offers.models import Offer
import os
from decimal import Decimal

def process_batch(batch_data):
    """Process a batch of product data"""
    results = {"success": 0, "errors": 0, "error_messages": []}
    
    for item in batch_data:
        try:
            # Get or create manufacturer
            manufacturer, _ = Manufacturer.objects.get_or_create(
                name=item['manufacturer'],
                defaults={'slug': item['manufacturer'].lower().replace(' ', '-')}
            )
            
            # Add logging to see what's happening
            print(f"Processing product: {item['mfr_part']} from {manufacturer.name}")
            
            # Clean and convert dimensional data - convert Decimal to float for JSON storage
            dimensions = {
                'length': float(clean_decimal(item.get('product_length')) or 0),
                'width': float(clean_decimal(item.get('product_width')) or 0),
                'height': float(clean_decimal(item.get('product_height')) or 0)
            }
            
            # Get or create product
            product, created = Product.objects.get_or_create(
                part_number=item['mfr_part'],
                manufacturer=manufacturer,
                defaults={
                    'name': item['name'][:255],  # Truncate to max field length
                    'slug': item['mfr_part'].lower().replace(' ', '-'),
                    'description': item.get('description', ''),
                    'specifications': {},  # Empty dict initially
                    'weight': clean_decimal(item.get('product_weight')),
                    'dimensions': dimensions,
                    'status': 'active',  # Set default status
                    'source': 'partner_import'  # Set source to match your enum
                }
            )
            
            print(f"Product {'created' if created else 'updated'}: {product.name}")
            
            # If product exists, update fields that might have changed
            if not created:
                product.name = item['name'][:255]  # Truncate to max field length
                product.description = item.get('description', '')
                product.weight = clean_decimal(item.get('product_weight'))
                product.dimensions = dimensions
                product.save()
            
            # Get vendor (assuming Synnex in this example)
            vendor, _ = Vendor.objects.get_or_create(
                code='synnex',
                defaults={'name': 'Synnex'}
            )
            
            # Clean price and quantity data
            cost_price = clean_decimal(item.get('initial_price', 0))
            msrp = clean_decimal(item.get('msrp'))
            stock_quantity = clean_integer(item.get('qty', 0))
            
            # Create or update offer - handle potential errors in price data
            if cost_price is not None:
                # Calculate selling price with markup - use Decimal for multiplication
                markup = Decimal('1.15')
                selling_price = cost_price * markup if cost_price else Decimal('0')
                
                offer, offer_created = Offer.objects.update_or_create(
                    product=product,
                    vendor=vendor,
                    defaults={
                        'cost_price': cost_price,
                        'selling_price': selling_price,
                        'msrp': msrp or cost_price,  # Ensure msrp is not None
                        'vendor_sku': item.get('reseller_part', '')[:100],  # Truncate to field length
                        'stock_quantity': stock_quantity,
                        'is_in_stock': stock_quantity > 0
                    }
                )
                print(f"Offer {'created' if offer_created else 'updated'} for {product.name}")
                
                # Handle category if we have category information
                if item.get('synnex_category_code'):
                    try:
                        # Create or get category
                        category_name = f"Synnex-{item['synnex_category_code']}"
                        category, _ = Category.objects.get_or_create(
                            slug=category_name.lower().replace(' ', '-'),
                            defaults={
                                'name': category_name
                            }
                        )
                        
                        # Associate product with category
                        ProductCategory.objects.get_or_create(
                            product=product,
                            category=category,
                            defaults={'is_primary': True}
                        )
                        print(f"Added product to category: {category.name}")
                    except Exception as cat_error:
                        print(f"Error adding category: {str(cat_error)}")
                
                results["success"] += 1
            else:
                results["errors"] += 1
                results["error_messages"].append(f"Invalid price data for {item['mfr_part']}")
                print(f"ERROR: Invalid price data for {item['mfr_part']}")
                
        except Exception as e:
            results["errors"] += 1
            error_msg = f"Error processing {item.get('mfr_part', 'unknown')}: {str(e)}"
            results["error_messages"].append(error_msg)
            print(f"ERROR: {error_msg}")
    
    return f"Processed {len(batch_data)} items: {results['success']} successes, {results['errors']} errors"

# Helper functions for data cleaning
def clean_decimal(value):
    """Convert value to Decimal or None if invalid"""
    from decimal import Decimal, InvalidOperation
    if value is None:
        return None
    
    try:
        # Remove any non-numeric characters except decimal point
        if isinstance(value, str):
            value = ''.join(c for c in value if c.isdigit() or c == '.')
            if not value:
                return None
        return Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None

def clean_integer(value):
    """Convert value to integer or 0 if invalid"""
    try:
        if value is None:
            return 0
        if isinstance(value, str):
            value = ''.join(c for c in value if c.isdigit())
            if not value:
                return 0
        return int(value)
    except (ValueError, TypeError):
        return 0

def check_tasks_and_send_email(task_ids):
    """Check if all import tasks are completed and send notification email"""
    from django_q.models import Success, Failure
    from django.core.mail import send_mail
    from django.conf import settings
    
    total_tasks = len(task_ids)
    
    # Fix: Change task_id__in to id__in
    completed_tasks = Success.objects.filter(id__in=task_ids).count()
    failed_tasks = Failure.objects.filter(id__in=task_ids).count()
    
    if completed_tasks + failed_tasks < total_tasks:
        # Not all tasks are finished yet
        return f"Progress: {completed_tasks}/{total_tasks} tasks completed, {failed_tasks} failed"
    
    # All tasks are finished
    success_percent = (completed_tasks / total_tasks) * 100
    
    # Send email notification
    subject = f"Product Import Completed - {success_percent:.1f}% Success"
    message = f"""
    Product import process has completed.
    
    Total tasks: {total_tasks}
    Successful: {completed_tasks}
    Failed: {failed_tasks}
    Success rate: {success_percent:.1f}%
    """
    
    recipient_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [recipient_email],
            fail_silently=False,
        )
        return "Email notification sent successfully"
    except Exception as e:
        return f"Error sending email notification: {str(e)}"