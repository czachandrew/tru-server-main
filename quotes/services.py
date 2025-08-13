import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, date
import PyPDF2
from io import BytesIO
import base64

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

class QuoteParsingService:
    """Service for parsing PDF quotes using OpenAI GPT-4 Vision API"""
    
    def __init__(self):
        # Get OpenAI API key from environment variable
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.client = OpenAI(api_key=api_key)
        self.max_file_size = 10 * 1024 * 1024  # 10MB
    
    def parse_pdf_quote(self, pdf_file_or_path, vendor_hints: Dict = None) -> Dict:
        """
        Parse a PDF quote using OpenAI GPT-4 Vision API
        
        Args:
            pdf_file_or_path: File object (Heroku) or path string (local dev)
            vendor_hints: Optional hints about vendor (name, company)
            
        Returns:
            Dict containing parsed quote data
        """
        import tempfile
        import os
        
        # Track if we created a temporary file for cleanup
        temp_file_path = None
        
        try:
            # Handle file paths (local dev), file objects (Django FieldFile), and raw content (Heroku)
            if isinstance(pdf_file_or_path, bytes):  # Raw PDF content from database
                logger.info(f"🌐 Processing raw PDF content ({len(pdf_file_or_path)} bytes)")
                
                # Create temporary file for processing
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                    tmp_file.write(pdf_file_or_path)
                    temp_file_path = tmp_file.name
                    pdf_file_path = temp_file_path
                
                cache_file = None  # Disable caching for temporary files
                logger.info(f"📄 Created temporary file from raw content: {pdf_file_path}")
                
            elif not isinstance(pdf_file_or_path, str):  # It's a file object (Django FieldFile)
                logger.info(f"🌐 Processing file object for Heroku compatibility")
                
                try:
                    # Try to read the file content - this will fail on Heroku if file doesn't exist
                    pdf_file_or_path.seek(0)
                    pdf_content = pdf_file_or_path.read()
                    
                    # Create temporary file for processing
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                        tmp_file.write(pdf_content)
                        temp_file_path = tmp_file.name
                        pdf_file_path = temp_file_path
                    
                    # Disable caching for temporary files
                    cache_file = None
                    logger.info(f"📄 Created temporary file: {pdf_file_path}")
                    
                except (FileNotFoundError, ValueError, IOError) as e:
                    logger.error(f"❌ Cannot access file object on Heroku: {str(e)}")
                    raise ValueError(f"File not accessible on Heroku ephemeral storage: {str(e)}")
                
            else:  # It's a file path string (local dev)
                logger.info(f"💻 Processing file path for local development")
                pdf_file_path = pdf_file_or_path
                cache_file = pdf_file_path + '.parsed_cache.json'
            
            # Check cache only for local dev
            if cache_file and os.path.exists(cache_file):
                logger.info(f"📁 Using cached parsing result for {pdf_file_path}")
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                    # Convert date strings back to date objects
                    if cached_data.get('quote_date'):
                        try:
                            from datetime import datetime
                            cached_data['quote_date'] = datetime.fromisoformat(cached_data['quote_date']).date()
                        except:
                            pass
                    return cached_data
            
            logger.info(f"🤖 Calling OpenAI API for {pdf_file_path}")
            
            # Convert PDF to images for Vision API
            pdf_images = self._convert_pdf_to_images(pdf_file_path)
            
            if not pdf_images:
                # Fallback to text extraction
                pdf_text = self._extract_text_from_pdf(pdf_file_path)
                if not pdf_text.strip():
                    raise ValueError("Could not extract content from PDF")
                result = self._parse_text_with_openai(pdf_text, vendor_hints)
            else:
                # Parse with Vision API
                result = self._parse_images_with_openai(pdf_images, vendor_hints)
            
            # Cache the result for faster debugging
            if cache_file:
                try:
                    import json
                    from datetime import date, datetime
                    from decimal import Decimal
                    
                    def serialize_for_cache(obj):
                        if isinstance(obj, (date, datetime)):
                            return obj.isoformat()
                        elif isinstance(obj, Decimal):
                            return float(obj)
                        elif isinstance(obj, dict):
                            return {k: serialize_for_cache(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [serialize_for_cache(item) for item in obj]
                        return obj
                    
                    with open(cache_file, 'w') as f:
                        json.dump(serialize_for_cache(result), f, indent=2)
                    logger.info(f"💾 Cached parsing result to {cache_file}")
                except Exception as cache_error:
                    logger.warning(f"Could not cache result: {cache_error}")
            
            # Clean up temporary file if we created one
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"🗑️ Cleaned up temporary file: {temp_file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Could not clean up temporary file: {cleanup_error}")
            
            return result
            
        except Exception as e:
            # Clean up temporary file on error
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"🗑️ Cleaned up temporary file after error: {temp_file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Could not clean up temporary file after error: {cleanup_error}")
            
            logger.error(f"Error parsing PDF quote: {str(e)}")
            raise
    
    def _convert_pdf_to_images(self, pdf_file_path: str) -> List[str]:
        """
        Convert PDF pages to base64 encoded images
        
        Returns:
            List of base64 encoded images
        """
        try:
            # For now, we'll use text extraction as a fallback
            # In production, you might want to use pdf2image library
            # pip install pdf2image (requires poppler-utils)
            
            # This is a simplified implementation
            # For Vision API, we would need proper image conversion
            return []
            
        except Exception as e:
            logger.warning(f"Could not convert PDF to images: {str(e)}")
            return []
    
    def _extract_text_from_pdf(self, pdf_file_path: str) -> str:
        """
        Extract text from PDF as fallback
        
        Returns:
            Extracted text content
        """
        try:
            with open(pdf_file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n"
                
                return text
                
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            raise
    
    def _parse_images_with_openai(self, images: List[str], vendor_hints: Dict = None) -> Dict:
        """
        Parse PDF images using OpenAI Vision API
        
        Args:
            images: List of base64 encoded images
            vendor_hints: Optional vendor information
            
        Returns:
            Parsed quote data
        """
        try:
            # Construct the prompt
            prompt = self._build_vision_prompt(vendor_hints)
            
            # Prepare messages for Vision API
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
            
            # Add images to the message
            for image in images[:5]:  # Limit to 5 images max
                messages[0]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image}"
                    }
                })
            
            # Call OpenAI Vision API
            response = self.client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=messages,
                max_tokens=2000,
                temperature=0.1
            )
            
            # Parse response
            response_text = response.choices[0].message.content
            return self._parse_openai_response(response_text)
            
        except Exception as e:
            logger.error(f"Error with OpenAI Vision API: {str(e)}")
            raise
    
    def _parse_text_with_openai(self, text: str, vendor_hints: Dict = None) -> Dict:
        """
        Parse PDF text using OpenAI GPT-4
        
        Args:
            text: Extracted PDF text
            vendor_hints: Optional vendor information
            
        Returns:
            Parsed quote data
        """
        try:
            # Construct the prompt
            prompt = self._build_text_prompt(vendor_hints)
            
            # Prepare messages
            messages = [
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": f"Please parse this quote text and return the data in the specified JSON format:\n\n{text}"
                }
            ]
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=messages,
                max_tokens=2000,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            response_text = response.choices[0].message.content
            return self._parse_openai_response(response_text)
            
        except Exception as e:
            logger.error(f"Error with OpenAI text API: {str(e)}")
            raise
    
    def _build_vision_prompt(self, vendor_hints: Dict = None) -> str:
        """Build prompt for Vision API"""
        
        hint_text = ""
        if vendor_hints:
            if vendor_hints.get('vendor_name'):
                hint_text += f"Vendor name hint: {vendor_hints['vendor_name']}\n"
            if vendor_hints.get('vendor_company'):
                hint_text += f"Vendor company hint: {vendor_hints['vendor_company']}\n"
        
        return f"""
You are an expert at parsing vendor quotes and purchase orders. Please analyze the provided PDF images and extract the following information in JSON format:

{hint_text}

Required JSON structure:
{{
    "vendor_name": "string - person/contact name",
    "vendor_company": "string - company name", 
    "quote_number": "string - quote/PO number",
    "quote_date": "YYYY-MM-DD - date of quote",
    "line_items": [
        {{
            "line_number": "number - line item number",
            "part_number": "string - manufacturer part number",
            "description": "string - product description",
            "manufacturer": "string - manufacturer name",
            "quantity": "number - quantity ordered",
            "unit_price": "number - price per unit",
            "total_price": "number - total line price",
            "vendor_sku": "string - vendor's SKU (optional)",
            "notes": "string - any additional notes (optional)"
        }}
    ],
    "subtotal": "number - subtotal amount",
    "tax": "number - tax amount (if any)",
    "shipping": "number - shipping amount (if any)",
    "total": "number - total amount",
    "extraction_confidence": "number 0-1 - confidence in extraction",
    "parsing_notes": "string - any notes about parsing challenges"
}}

Important parsing guidelines:
1. Be very careful with numbers - preserve decimal places
2. Extract exact part numbers as they appear
3. If information is unclear or missing, use null
4. Focus on line items - that's the most important data
5. Look for manufacturer names carefully (often in small text)
6. Return valid JSON only, no other text
"""
    
    def _build_text_prompt(self, vendor_hints: Dict = None) -> str:
        """Build prompt for text-based parsing"""
        
        hint_text = ""
        if vendor_hints:
            if vendor_hints.get('vendor_name'):
                hint_text += f"Vendor name hint: {vendor_hints['vendor_name']}\n"
            if vendor_hints.get('vendor_company'):
                hint_text += f"Vendor company hint: {vendor_hints['vendor_company']}\n"
        
        return f"""
You are an expert at parsing vendor quotes and purchase orders from text. Extract information and return it in JSON format.

{hint_text}

Return a JSON object with this exact structure:
{{
    "vendor_name": "string - person/contact name or null",
    "vendor_company": "string - company name or null", 
    "quote_number": "string - quote/PO number or null",
    "quote_date": "YYYY-MM-DD - date of quote or null",
    "line_items": [
        {{
            "line_number": "number - line item number or null",
            "part_number": "string - manufacturer part number",
            "description": "string - product description",
            "manufacturer": "string - manufacturer name or null",
            "quantity": "number - quantity ordered",
            "unit_price": "number - price per unit",
            "total_price": "number - total line price",
            "vendor_sku": "string - vendor's SKU or null",
            "notes": "string - any additional notes or null"
        }}
    ],
    "subtotal": "number - subtotal amount or null",
    "tax": "number - tax amount or null",
    "shipping": "number - shipping amount or null", 
    "total": "number - total amount or null",
    "extraction_confidence": "number 0-1 - confidence in extraction",
    "parsing_notes": "string - any notes about parsing challenges or null"
}}

Guidelines:
1. Be extremely careful with numerical values
2. Extract part numbers exactly as they appear
3. Use null for missing information
4. Return only valid JSON, no other text
5. Focus on finding all line items
"""
    
    def _parse_openai_response(self, response_text: str) -> Dict:
        """
        Parse and validate OpenAI response
        
        Args:
            response_text: Raw response from OpenAI
            
        Returns:
            Validated and cleaned quote data
        """
        try:
            # Parse JSON response
            data = json.loads(response_text)
            
            # Validate and clean the data
            cleaned_data = self._clean_quote_data(data)
            
            return cleaned_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse OpenAI JSON response: {str(e)}")
            logger.error(f"Response text: {response_text}")
            raise ValueError("Invalid JSON response from OpenAI")
    
    def _clean_quote_data(self, data: Dict) -> Dict:
        """
        Clean and validate quote data from OpenAI
        
        Args:
            data: Raw data from OpenAI
            
        Returns:
            Cleaned and validated data
        """
        cleaned = {
            'vendor_name': self._clean_string(data.get('vendor_name')),
            'vendor_company': self._clean_string(data.get('vendor_company')),
            'quote_number': self._clean_string(data.get('quote_number')),
            'quote_date': self._parse_date(data.get('quote_date')),
            'line_items': [],
            'subtotal': self._parse_decimal(data.get('subtotal')),
            'tax': self._parse_decimal(data.get('tax')),
            'shipping': self._parse_decimal(data.get('shipping')),
            'total': self._parse_decimal(data.get('total')),
            'extraction_confidence': min(1.0, max(0.0, float(data.get('extraction_confidence', 0.8)))),
            'parsing_notes': self._clean_string(data.get('parsing_notes'))
        }
        
        # Clean line items
        for item in data.get('line_items', []):
            cleaned_item = {
                'line_number': self._parse_int(item.get('line_number')),
                'part_number': self._clean_string(item.get('part_number'), required=True),
                'description': self._clean_string(item.get('description'), required=True),
                'manufacturer': self._clean_string(item.get('manufacturer')),
                'quantity': self._parse_int(item.get('quantity'), default=1),
                'unit_price': self._parse_decimal(item.get('unit_price')),
                'total_price': self._parse_decimal(item.get('total_price')),
                'vendor_sku': self._clean_string(item.get('vendor_sku')),
                'notes': self._clean_string(item.get('notes'))
            }
            
            # Calculate total_price if missing
            if not cleaned_item['total_price'] and cleaned_item['unit_price'] and cleaned_item['quantity']:
                cleaned_item['total_price'] = cleaned_item['unit_price'] * cleaned_item['quantity']
            
            cleaned['line_items'].append(cleaned_item)
        
        return cleaned
    
    def _clean_string(self, value, required=False) -> Optional[str]:
        """Clean and validate string value"""
        if value is None or value == '':
            if required:
                raise ValueError("Required string field is missing")
            return None
        
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned if cleaned else None
        
        return str(value).strip() if str(value).strip() else None
    
    def _parse_decimal(self, value) -> Optional[Decimal]:
        """Parse decimal value safely"""
        if value is None or value == '':
            return None
        
        try:
            # Handle string values
            if isinstance(value, str):
                # Remove currency symbols and commas
                cleaned = value.replace('$', '').replace(',', '').replace(' ', '')
                if not cleaned:
                    return None
                return Decimal(cleaned)
            
            return Decimal(str(value))
        except:
            return None
    
    def _parse_int(self, value, default=None) -> Optional[int]:
        """Parse integer value safely"""
        if value is None or value == '':
            return default
        
        try:
            if isinstance(value, str):
                cleaned = value.replace(',', '').replace(' ', '')
                if not cleaned:
                    return default
                return int(float(cleaned))  # Handle floats that should be ints
            
            return int(value)
        except:
            return default
    
    def _parse_date(self, value) -> Optional[date]:
        """Parse date value safely"""
        if not value:
            return None
        
        try:
            if isinstance(value, str):
                # Try different date formats
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y']:
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
            
            return None
        except:
            return None
