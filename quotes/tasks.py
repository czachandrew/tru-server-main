from django_q.tasks import async_task
from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from decimal import Decimal
import logging
import os
from typing import Dict, List, Optional

from quotes.models import Quote, QuoteItem, ProductMatch, VendorPricing
from quotes.services import QuoteParsingService
from products.models import Product, Manufacturer
from vendors.models import Vendor
from offers.models import Offer

logger = logging.getLogger(__name__)

def process_quote_pdf(quote_id: int) -> dict:
    """
    Django Q task to process a PDF quote with OpenAI
    
    Args:
        quote_id: ID of the quote to process
        
    Returns:
        dict: Processing results
    """
    logger.info(f"🎯 Processing quote PDF for ID: {quote_id}")
    
    try:
        quote = Quote.objects.get(id=quote_id)
        
        # Update status
        quote.status = 'parsing'
        quote.save()
        
        # Initialize parsing service
        parsing_service = QuoteParsingService()
        
        # Prepare vendor hints
        vendor_hints = {}
        if quote.vendor_name:
            vendor_hints['vendor_name'] = quote.vendor_name
        if quote.vendor_company:
            vendor_hints['vendor_company'] = quote.vendor_company
        
        # Parse the PDF
        try:
            logger.info(f"🔍 Starting PDF parsing for quote {quote_id}")
            
            # Try to use file path for local development, stored content for Heroku
            if quote.pdf_content:
                # Use stored PDF content (Heroku)
                pdf_input = quote.pdf_content
                logger.info(f"📄 Using stored PDF content ({len(quote.pdf_content)} bytes)")
            else:
                # Try file path for local development
                try:
                    pdf_path = quote.pdf_file.path
                    logger.info(f"🔍 Checking file path: {pdf_path}")
                    
                    if os.path.exists(pdf_path):
                        pdf_input = pdf_path
                        logger.info(f"📄 PDF file path (local): {pdf_input}")
                    else:
                        # File path doesn't exist - use file object
                        pdf_input = quote.pdf_file
                        logger.info(f"📄 PDF file object: {pdf_input.name} - path {pdf_path} does not exist")
                except (ValueError, AttributeError) as e:
                    # Fallback to file object
                    pdf_input = quote.pdf_file
                    logger.info(f"📄 PDF file object (fallback): {pdf_input.name} - exception: {e}")
            
            logger.info(f"💡 Vendor hints: {vendor_hints}")
            
            parsed_data = parsing_service.parse_pdf_quote(
                pdf_input, 
                vendor_hints
            )
            
            logger.info(f"✅ PDF parsing completed for quote {quote_id}")
            logger.info(f"📊 Extracted {len(parsed_data.get('line_items', []))} line items")
            logger.info(f"💰 Total: ${parsed_data.get('total', 'N/A')}")
            
        except Exception as parsing_error:
            quote.status = 'error'
            quote.parsing_error = f"PDF parsing failed: {str(parsing_error)}"
            quote.save()
            
            logger.error(f"❌ PDF parsing failed for quote {quote_id}: {str(parsing_error)}")
            try:
                logger.error(f"📄 File path: {quote.pdf_file.path}")
            except:
                logger.error(f"📄 File object: {quote.pdf_file.name}")
            logger.error(f"💡 Vendor hints: {vendor_hints}")
            
            import traceback
            logger.error(f"🐛 Full traceback: {traceback.format_exc()}")
            
            return {
                'success': False,
                'error_message': str(parsing_error),
                'quote_id': quote_id
            }
        
        # Store raw response for debugging (convert dates to strings for JSON serialization)
        import json
        from datetime import date, datetime
        from decimal import Decimal
        
        def serialize_for_json(obj):
            """Convert non-JSON-serializable objects to JSON-compatible formats"""
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            elif isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, dict):
                return {k: serialize_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [serialize_for_json(item) for item in obj]
            return obj
        
        # Log the raw response structure for debugging
        logger.info(f"📋 Raw parsed data keys: {list(parsed_data.keys())}")
        logger.info(f"🔍 Sample line item: {parsed_data.get('line_items', [{}])[0] if parsed_data.get('line_items') else 'None'}")
        
        try:
            # Test serialization before storing
            json.dumps(serialize_for_json(parsed_data))
            logger.info("✅ JSON serialization test passed")
        except Exception as serialize_error:
            logger.error(f"❌ JSON serialization test failed: {str(serialize_error)}")
            logger.error(f"🐛 Problematic data structure: {type(parsed_data)}")
            # Log the structure that's causing issues
            for key, value in parsed_data.items():
                logger.error(f"   {key}: {type(value)} = {value}")
            raise
        
        quote.raw_openai_response = serialize_for_json(parsed_data)
        
        # Update quote with parsed metadata
        if parsed_data.get('vendor_name') and not quote.vendor_name:
            quote.vendor_name = parsed_data['vendor_name']
        
        if parsed_data.get('vendor_company') and not quote.vendor_company:
            quote.vendor_company = parsed_data['vendor_company']
        
        if parsed_data.get('quote_number'):
            quote.quote_number = parsed_data['quote_number']
        
        if parsed_data.get('quote_date'):
            quote.quote_date = parsed_data['quote_date']
        
        if parsed_data.get('subtotal'):
            quote.subtotal = parsed_data['subtotal']
        
        if parsed_data.get('tax'):
            quote.tax = parsed_data['tax']
        
        if parsed_data.get('shipping'):
            quote.shipping = parsed_data['shipping']
        
        if parsed_data.get('total'):
            quote.total = parsed_data['total']
        
        quote.save()
        
        # Create quote items
        created_items = 0
        for item_data in parsed_data.get('line_items', []):
            try:
                # Serialize the raw data for storage
                serialized_item_data = serialize_for_json(item_data)
                
                quote_item = QuoteItem.objects.create(
                    quote=quote,
                    line_number=item_data.get('line_number'),
                    part_number=item_data['part_number'],
                    description=item_data['description'],
                    manufacturer=item_data.get('manufacturer', ''),
                    quantity=item_data['quantity'],
                    unit_price=item_data.get('unit_price', 0),
                    total_price=item_data.get('total_price', 0),
                    vendor_sku=item_data.get('vendor_sku') or '',  # Convert None to empty string
                    notes=item_data.get('notes') or '',           # Convert None to empty string
                    extraction_confidence=parsed_data.get('extraction_confidence', 0.8),
                    raw_extracted_data=serialized_item_data
                )
                created_items += 1
                logger.info(f"✅ Created quote item: {item_data['part_number']} - {item_data['description'][:50]}...")
                
            except Exception as item_error:
                logger.error(f"❌ Failed to create quote item: {str(item_error)}")
                logger.error(f"🐛 Item data: {item_data}")
                logger.error(f"🔍 Data types: {[(k, type(v)) for k, v in item_data.items()]}")
                continue
        
        if created_items == 0:
            quote.status = 'error'
            quote.parsing_error = "No valid line items could be extracted from the PDF"
            quote.save()
            
            return {
                'success': False,
                'error_message': "No valid line items extracted",
                'quote_id': quote_id
            }
        
        # Update status to matching
        quote.status = 'matching'
        quote.processed_at = timezone.now()
        quote.save()
        
        # Start product matching (this will also create offers)
        async_task(
            'quotes.tasks.match_quote_products',
            quote_id,
            quote.demo_mode_enabled,
            group='quote_matching',
            timeout=180
        )
        
        logger.info(f"✅ Quote PDF processing completed for {quote_id}: {created_items} items created")
        
        return {
            'success': True,
            'items_created': created_items,
            'quote_id': quote_id,
            'extraction_confidence': parsed_data.get('extraction_confidence', 0.8)
        }
        
    except Quote.DoesNotExist:
        error_msg = f"Quote {quote_id} not found"
        logger.error(error_msg)
        return {
            'success': False,
            'error_message': error_msg,
            'quote_id': quote_id
        }
    
    except Exception as e:
        error_msg = f"Unexpected error in PDF processing: {str(e)}"
        logger.error(error_msg)
        
        try:
            quote = Quote.objects.get(id=quote_id)
            quote.status = 'error'
            quote.parsing_error = error_msg
            quote.save()
        except:
            pass
        
        return {
            'success': False,
            'error_message': error_msg,
            'quote_id': quote_id
        }

def match_quote_products(quote_id: int, demo_mode: bool = False) -> dict:
    """
    Django Q task to match quote items with products in the database
    
    Args:
        quote_id: ID of the quote to process
        demo_mode: Whether to enable demo mode for superior pricing
        
    Returns:
        dict: Matching results
    """
    logger.info(f"🎯 Matching products for quote ID: {quote_id}, demo_mode: {demo_mode}")
    
    try:
        quote = Quote.objects.get(id=quote_id)
        
        # Update status
        quote.status = 'matching'
        quote.save()
        
        # Get all quote items
        quote_items = quote.items.all()
        
        if not quote_items.exists():
            quote.status = 'error'
            quote.parsing_error = "No quote items to match"
            quote.save()
            
            return {
                'success': False,
                'error_message': "No quote items to match",
                'quote_id': quote_id
            }
        
        matching_service = ProductMatchingService()
        total_items = quote_items.count()
        matched_count = 0
        demo_products_created = 0
        
        # Process each quote item
        for quote_item in quote_items:
            try:
                # Clear existing matches
                quote_item.matches.all().delete()
                
                # Find product matches
                matches = matching_service.find_product_matches(quote_item, demo_mode)
                
                # Create ProductMatch records
                for match_data in matches:
                    ProductMatch.objects.create(
                        quote_item=quote_item,
                        product=match_data.get('product'),
                        confidence=match_data['confidence'],
                        is_exact_match=match_data.get('is_exact_match', False),
                        match_method=match_data['match_method'],
                        price_difference=match_data.get('price_difference', 0),
                        price_difference_percentage=match_data.get('price_difference_percentage', 0),
                        is_demo_price=match_data.get('is_demo_price', False),
                        demo_generated_product=match_data.get('demo_generated_product', False),
                        suggested_product=match_data.get('suggested_product'),
                        match_details=match_data.get('match_details', {})
                    )
                
                if matches:
                    matched_count += 1
                    
                    # Count demo products created
                    demo_products_created += sum(1 for m in matches if m.get('demo_generated_product'))
                    
                    # Create vendor pricing record for intelligence
                    if quote_item.unit_price and quote_item.part_number:
                        try:
                            # Try to link to existing vendor
                            vendor = None
                            if quote.vendor_company:
                                vendor = find_or_create_vendor(quote.vendor_company)
                            
                            # Find the best matched product
                            best_match = max(matches, key=lambda x: x['confidence'])
                            if best_match.get('product'):
                                VendorPricing.objects.get_or_create(
                                    source_quote=quote,
                                    source_quote_item=quote_item,
                                    defaults={
                                        'product': best_match['product'],
                                        'vendor_company': quote.vendor_company or 'Unknown',
                                        'vendor_name': quote.vendor_name or '',
                                        'quoted_price': quote_item.unit_price,
                                        'quantity': quote_item.quantity,
                                        'quote_date': quote.quote_date or quote.created_at.date(),
                                        'part_number_used': quote_item.part_number,
                                        'is_confirmed': False
                                    }
                                )
                        except Exception as pricing_error:
                            logger.warning(f"Failed to create vendor pricing record: {str(pricing_error)}")
                
            except Exception as item_error:
                logger.warning(f"Failed to match quote item {quote_item.id}: {str(item_error)}")
                continue
        
        # Create offers from matched quote items
        offers_created = create_offers_from_quote_items(quote)
        
        # Update quote status
        quote.status = 'completed'
        quote.processed_at = timezone.now()
        quote.save()
        
        logger.info(f"✅ Product matching completed for quote {quote_id}: {matched_count}/{total_items} items matched, {offers_created} offers created")
        
        return {
            'success': True,
            'total_items': total_items,
            'matched_items': matched_count,
            'demo_products_created': demo_products_created,
            'quote_id': quote_id
        }
        
    except Quote.DoesNotExist:
        error_msg = f"Quote {quote_id} not found"
        logger.error(error_msg)
        return {
            'success': False,
            'error_message': error_msg,
            'quote_id': quote_id
        }
    
    except Exception as e:
        error_msg = f"Unexpected error in product matching: {str(e)}"
        logger.error(error_msg)
        
        try:
            quote = Quote.objects.get(id=quote_id)
            quote.status = 'error'
            quote.parsing_error = error_msg
            quote.save()
        except:
            pass
        
        return {
            'success': False,
            'error_message': error_msg,
            'quote_id': quote_id
        }

class ProductMatchingService:
    """Service for matching quote items with products in the database"""
    
    def find_product_matches(self, quote_item: QuoteItem, demo_mode: bool = False) -> List[Dict]:
        """
        Find product matches for a quote item
        
        Args:
            quote_item: QuoteItem to match
            demo_mode: Whether to enable demo mode
            
        Returns:
            List of match dictionaries
        """
        matches = []
        
        # 1. Exact part number match
        exact_matches = self._find_exact_part_number_matches(quote_item)
        matches.extend(exact_matches)
        
        # 2. Fuzzy part number match (if no exact matches)
        if not exact_matches:
            fuzzy_matches = self._find_fuzzy_part_number_matches(quote_item)
            matches.extend(fuzzy_matches)
        
        # 3. Manufacturer + description match
        if not matches or len(matches) < 3:
            mfg_matches = self._find_manufacturer_matches(quote_item)
            matches.extend(mfg_matches)
        
        # 4. Description similarity match
        if not matches or len(matches) < 2:
            desc_matches = self._find_description_matches(quote_item)
            matches.extend(desc_matches)
        
        # 5. Demo mode - create superior product if no good matches
        if demo_mode and (not matches or max(m['confidence'] for m in matches) < 0.7):
            demo_match = self._create_demo_product_match(quote_item)
            if demo_match:
                matches.append(demo_match)
        
        # Sort by confidence and return top matches
        matches.sort(key=lambda x: (x['is_exact_match'], x['confidence']), reverse=True)
        return matches[:5]  # Return top 5 matches
    
    def _find_exact_part_number_matches(self, quote_item: QuoteItem) -> List[Dict]:
        """Find products with exact part number match"""
        matches = []
        
        try:
            products = Product.objects.filter(
                part_number__iexact=quote_item.part_number,
                status='active'
            )
            
            for product in products:
                confidence = 1.0
                
                # Boost confidence if manufacturer also matches
                if (quote_item.manufacturer and product.manufacturer.name and 
                    quote_item.manufacturer.lower() in product.manufacturer.name.lower()):
                    confidence = 1.0
                
                price_diff, price_diff_pct = self._calculate_price_difference(quote_item, product)
                
                matches.append({
                    'product': product,
                    'confidence': confidence,
                    'is_exact_match': True,
                    'match_method': 'exact_part_number',
                    'price_difference': price_diff,
                    'price_difference_percentage': price_diff_pct,
                    'match_details': {
                        'matched_part_number': product.part_number,
                        'manufacturer_match': quote_item.manufacturer.lower() in product.manufacturer.name.lower() if quote_item.manufacturer else False
                    }
                })
        
        except Exception as e:
            logger.warning(f"Error in exact part number matching: {str(e)}")
        
        return matches
    
    def _find_fuzzy_part_number_matches(self, quote_item: QuoteItem) -> List[Dict]:
        """Find products with similar part numbers"""
        matches = []
        
        try:
            # Simple fuzzy matching - remove common separators and compare
            clean_part = quote_item.part_number.replace('-', '').replace('_', '').replace(' ', '').upper()
            
            products = Product.objects.filter(
                Q(part_number__icontains=quote_item.part_number[:6]) |  # First 6 chars
                Q(part_number__icontains=clean_part[:6]),
                status='active'
            ).exclude(part_number__iexact=quote_item.part_number)[:10]
            
            for product in products:
                clean_product_part = product.part_number.replace('-', '').replace('_', '').replace(' ', '').upper()
                
                # Calculate similarity
                similarity = self._calculate_string_similarity(clean_part, clean_product_part)
                
                if similarity > 0.7:  # 70% similarity threshold
                    confidence = similarity * 0.9  # Lower than exact match
                    
                    # Boost if manufacturer matches
                    if (quote_item.manufacturer and product.manufacturer.name and 
                        quote_item.manufacturer.lower() in product.manufacturer.name.lower()):
                        confidence = min(1.0, confidence + 0.1)
                    
                    price_diff, price_diff_pct = self._calculate_price_difference(quote_item, product)
                    
                    matches.append({
                        'product': product,
                        'confidence': confidence,
                        'is_exact_match': False,
                        'match_method': 'fuzzy_part_number',
                        'price_difference': price_diff,
                        'price_difference_percentage': price_diff_pct,
                        'match_details': {
                            'similarity_score': similarity,
                            'matched_part_number': product.part_number
                        }
                    })
        
        except Exception as e:
            logger.warning(f"Error in fuzzy part number matching: {str(e)}")
        
        return matches
    
    def _find_manufacturer_matches(self, quote_item: QuoteItem) -> List[Dict]:
        """Find products by manufacturer and description keywords"""
        matches = []
        
        if not quote_item.manufacturer:
            return matches
        
        try:
            # Find manufacturer
            manufacturers = Manufacturer.objects.filter(
                name__icontains=quote_item.manufacturer
            )
            
            if not manufacturers:
                return matches
            
            # Extract keywords from description
            keywords = self._extract_keywords(quote_item.description)
            
            for manufacturer in manufacturers:
                products = Product.objects.filter(
                    manufacturer=manufacturer,
                    status='active'
                )
                
                # Filter by description keywords
                for keyword in keywords[:3]:  # Top 3 keywords
                    products = products.filter(
                        Q(name__icontains=keyword) |
                        Q(description__icontains=keyword)
                    )
                
                for product in products[:5]:  # Top 5 matches
                    confidence = 0.6  # Base confidence for manufacturer match
                    
                    # Calculate description similarity
                    desc_similarity = self._calculate_string_similarity(
                        quote_item.description.lower(),
                        (product.name + ' ' + (product.description or '')).lower()
                    )
                    
                    confidence = min(1.0, confidence + (desc_similarity * 0.3))
                    
                    price_diff, price_diff_pct = self._calculate_price_difference(quote_item, product)
                    
                    matches.append({
                        'product': product,
                        'confidence': confidence,
                        'is_exact_match': False,
                        'match_method': 'manufacturer_match',
                        'price_difference': price_diff,
                        'price_difference_percentage': price_diff_pct,
                        'match_details': {
                            'manufacturer_name': manufacturer.name,
                            'description_similarity': desc_similarity,
                            'matched_keywords': keywords[:3]
                        }
                    })
        
        except Exception as e:
            logger.warning(f"Error in manufacturer matching: {str(e)}")
        
        return matches
    
    def _find_description_matches(self, quote_item: QuoteItem) -> List[Dict]:
        """Find products by description similarity"""
        matches = []
        
        try:
            keywords = self._extract_keywords(quote_item.description)
            
            if not keywords:
                return matches
            
            # Search products by keywords
            query = Q()
            for keyword in keywords[:5]:  # Top 5 keywords
                query |= Q(name__icontains=keyword) | Q(description__icontains=keyword)
            
            products = Product.objects.filter(query, status='active')[:20]
            
            for product in products:
                # Calculate description similarity
                desc_similarity = self._calculate_string_similarity(
                    quote_item.description.lower(),
                    (product.name + ' ' + (product.description or '')).lower()
                )
                
                if desc_similarity > 0.4:  # 40% similarity threshold
                    confidence = desc_similarity * 0.7  # Lower confidence for description-only match
                    
                    price_diff, price_diff_pct = self._calculate_price_difference(quote_item, product)
                    
                    matches.append({
                        'product': product,
                        'confidence': confidence,
                        'is_exact_match': False,
                        'match_method': 'description_similarity',
                        'price_difference': price_diff,
                        'price_difference_percentage': price_diff_pct,
                        'match_details': {
                            'description_similarity': desc_similarity,
                            'matched_keywords': keywords[:5]
                        }
                    })
        
        except Exception as e:
            logger.warning(f"Error in description matching: {str(e)}")
        
        return matches
    
    def _create_demo_product_match(self, quote_item: QuoteItem) -> Optional[Dict]:
        """Create a demo product with superior pricing"""
        
        try:
            # Create or get manufacturer
            manufacturer = None
            if quote_item.manufacturer:
                manufacturer, created = Manufacturer.objects.get_or_create(
                    name=quote_item.manufacturer,
                    defaults={'slug': quote_item.manufacturer.lower().replace(' ', '-')}
                )
            else:
                manufacturer, created = Manufacturer.objects.get_or_create(
                    name="Demo Manufacturer",
                    defaults={'slug': 'demo-manufacturer'}
                )
            
            # Create demo product
            demo_product = Product.objects.create(
                name=f"DEMO: {quote_item.description[:100]}",
                slug=f"demo-{quote_item.part_number.lower().replace(' ', '-')}-{quote_item.id}",
                description=f"Demo product for quote analysis: {quote_item.description}",
                manufacturer=manufacturer,
                part_number=quote_item.part_number,
                status='active',
                is_demo=True,
                source='demo'
            )
            
            # Calculate superior pricing (20% better)
            if quote_item.unit_price:
                superior_price = quote_item.unit_price * Decimal('0.8')  # 20% better
                price_difference = superior_price - quote_item.unit_price
                price_diff_pct = -20.0  # 20% savings
            else:
                superior_price = Decimal('0')
                price_difference = Decimal('0')
                price_diff_pct = 0.0
            
            return {
                'product': demo_product,
                'confidence': 0.95,  # High confidence for demo
                'is_exact_match': False,
                'match_method': 'demo_generated',
                'price_difference': price_difference,
                'price_difference_percentage': price_diff_pct,
                'is_demo_price': True,
                'demo_generated_product': True,
                'match_details': {
                    'demo_pricing_discount': 20,
                    'original_price': float(quote_item.unit_price) if quote_item.unit_price else 0,
                    'demo_price': float(superior_price)
                }
            }
        
        except Exception as e:
            logger.warning(f"Error creating demo product: {str(e)}")
            return None
    
    def _calculate_price_difference(self, quote_item: QuoteItem, product: Product) -> tuple:
        """Calculate price difference between quote and our pricing"""
        
        if not quote_item.unit_price:
            return Decimal('0'), 0.0
        
        # Get best offer for the product
        best_offer = product.offers.filter(is_active=True).order_by('selling_price').first()
        
        if not best_offer:
            return Decimal('0'), 0.0
        
        price_diff = best_offer.selling_price - quote_item.unit_price
        price_diff_pct = float((price_diff / quote_item.unit_price) * 100)
        
        return price_diff, price_diff_pct
    
    def _calculate_string_similarity(self, str1: str, str2: str) -> float:
        """Calculate simple string similarity (Jaccard similarity)"""
        
        if not str1 or not str2:
            return 0.0
        
        # Convert to sets of words
        words1 = set(str1.lower().split())
        words2 = set(str2.lower().split())
        
        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text"""
        
        if not text:
            return []
        
        # Simple keyword extraction
        words = text.lower().split()
        
        # Remove common stopwords
        stopwords = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an'}
        
        keywords = [word for word in words if word not in stopwords and len(word) > 2]
        
        # Return unique keywords
        return list(dict.fromkeys(keywords))

def find_or_create_vendor(vendor_company: str) -> Optional[Vendor]:
    """Find or create a vendor by company name"""
    
    try:
        # Try exact match first
        vendor = Vendor.objects.filter(name__iexact=vendor_company).first()
        
        if vendor:
            return vendor
        
        # Try partial match
        vendor = Vendor.objects.filter(name__icontains=vendor_company).first()
        
        if vendor:
            return vendor
        
        # Create new vendor
        vendor = Vendor.objects.create(
            name=vendor_company,
            code=vendor_company[:10].upper().replace(' ', ''),
            vendor_type='supplier',
            is_active=True
        )
        
        return vendor
    
    except Exception as e:
        logger.warning(f"Error finding/creating vendor: {str(e)}")
        return None


def create_offers_from_quote_items(quote: Quote) -> int:
    """
    Create Offer objects from quote items with matched products
    
    Args:
        quote: Quote object to process
        
    Returns:
        int: Number of offers created
    """
    offers_created = 0
    
    for quote_item in quote.items.all():
        # Only create offers for items with product matches
        for match in quote_item.matches.filter(product__isnull=False):
            try:
                # Find or create vendor
                vendor = None
                if quote.vendor_company:
                    vendor = find_or_create_vendor(quote.vendor_company)
                else:
                    # Create a generic vendor for this quote
                    vendor, _ = Vendor.objects.get_or_create(
                        name=quote.vendor_name or f"Quote Vendor {quote.id}",
                        code=f"QUOTE_{quote.id}",
                        defaults={'is_active': True}
                    )
                
                # Create or update offer
                offer, created = Offer.objects.get_or_create(
                    product=match.product,
                    vendor=vendor,
                    offer_type='quote',
                    source_quote=quote,
                    defaults={
                        'selling_price': quote_item.unit_price,
                        'vendor_sku': quote_item.part_number,
                        'stock_quantity': quote_item.quantity,
                        'is_in_stock': True,
                        'is_active': True,
                        'is_confirmed': False,  # Mark as unconfirmed quote pricing
                    }
                )
                
                if created:
                    offers_created += 1
                    logger.info(f"📦 Created quote offer: {match.product.name} - ${quote_item.unit_price}")
                else:
                    # Update existing offer with new pricing
                    offer.selling_price = quote_item.unit_price
                    offer.stock_quantity = quote_item.quantity
                    offer.save()
                    logger.info(f"📦 Updated quote offer: {match.product.name} - ${quote_item.unit_price}")
                
            except Exception as e:
                logger.warning(f"Failed to create offer for quote item {quote_item.id}: {str(e)}")
                continue
    
    logger.info(f"🏪 Created {offers_created} offers from quote {quote.id}")
    return offers_created


# Utility function for serializing dates and decimals
def serialize_for_json(obj):
    """Convert dates and decimals to JSON-serializable types"""
    from datetime import date, datetime
    from decimal import Decimal
    
    if isinstance(obj, dict):
        return {key: serialize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj
