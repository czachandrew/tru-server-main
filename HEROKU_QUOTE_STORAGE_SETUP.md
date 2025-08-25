# Heroku Quote Storage Setup Guide

## 🚨 **CRITICAL: Current Status**

**❌ Quote parsing will NOT work on Heroku** without fixing file storage!

**Why?** The quote parsing system uses local file paths (`quote.pdf_file.path`) which don't work on Heroku's ephemeral file system.

## ⚡ **Quick Fix for Testing (Option 1)**

### Update quotes/tasks.py:
```python
# Change line 52 from:
parsed_data = parsing_service.parse_pdf_quote(
    quote.pdf_file.path,  # ❌ Fails on Heroku
    vendor_hints
)

# To:
parsed_data = parsing_service.parse_pdf_quote(
    quote.pdf_file,  # ✅ Pass file object
    vendor_hints
)
```

### Update quotes/services.py:
```python
def parse_pdf_quote(self, pdf_file, vendor_hints: Dict = None) -> Dict:
    """
    Parse a PDF quote using OpenAI GPT-4 Vision API
    
    Args:
        pdf_file: File object or path to the PDF file
        vendor_hints: Optional hints about vendor (name, company)
    """
    import tempfile
    import os
    
    try:
        # Handle both file objects (Heroku) and file paths (local dev)
        if hasattr(pdf_file, 'read'):  # It's a file object
            logger.info(f"🌐 Processing file object for Heroku")
            
            # Reset file pointer and read content
            pdf_file.seek(0)
            pdf_content = pdf_file.read()
            
            # Create temporary file for processing
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(pdf_content)
                pdf_file_path = tmp_file.name
            
            # Disable caching for temporary files
            cache_file = None
            
        else:  # It's a file path (local dev)
            logger.info(f"💻 Processing file path for local dev")
            pdf_file_path = pdf_file
            cache_file = pdf_file_path + '.parsed_cache.json'
        
        # Check cache only for local dev
        if cache_file and os.path.exists(cache_file):
            logger.info(f"📁 Using cached parsing result")
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
        
        # ... rest of OpenAI processing ...
        
        # Cache only for local dev
        if cache_file:
            with open(cache_file, 'w') as f:
                json.dump(serialize_for_cache(result), f, indent=2)
            logger.info(f"💾 Cached parsing result to {cache_file}")
        
        # Clean up temporary file for Heroku
        if hasattr(pdf_file, 'read') and os.path.exists(pdf_file_path):
            os.unlink(pdf_file_path)
            logger.info(f"🗑️ Cleaned up temporary file")
        
        return result
        
    except Exception as e:
        # Clean up temporary file on error
        if hasattr(pdf_file, 'read') and 'pdf_file_path' in locals() and os.path.exists(pdf_file_path):
            os.unlink(pdf_file_path)
        raise
```

## 🏗️ **Proper S3 Setup (Option 2 - Recommended)**

### 1. Install required packages:
```bash
pip install django-storages boto3
```

### 2. Add to requirements.txt:
```
django-storages>=1.14.0
boto3>=1.34.0
```

### 3. Update settings.py:
```python
# Add to INSTALLED_APPS
INSTALLED_APPS = [
    # ... existing apps ...
    'storages',
]

# S3 Configuration
if os.environ.get('USE_S3') == 'True':
    # S3 settings
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_DEFAULT_ACL = 'private'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    
    # Static files
    STATICFILES_STORAGE = 'storages.backends.s3boto3.StaticS3Boto3Storage'
    AWS_STATIC_LOCATION = 'static'
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_STATIC_LOCATION}/'
    
    # Media files
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.PrivateMediaS3Boto3Storage'
    AWS_MEDIA_LOCATION = 'media'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/'
else:
    # Local development settings
    MEDIA_URL = '/media/'
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
```

### 4. Create custom storage backend:
```python
# Create storages_backends.py
from storages.backends.s3boto3 import S3Boto3Storage

class PrivateMediaS3Boto3Storage(S3Boto3Storage):
    location = 'media'
    default_acl = 'private'
    file_overwrite = False
    custom_domain = False
```

### 5. Set Heroku environment variables:
```bash
heroku config:set USE_S3=True -a tru-prime
heroku config:set AWS_ACCESS_KEY_ID=your_access_key -a tru-prime
heroku config:set AWS_SECRET_ACCESS_KEY=your_secret_key -a tru-prime
heroku config:set AWS_STORAGE_BUCKET_NAME=your_bucket_name -a tru-prime
heroku config:set AWS_S3_REGION_NAME=us-east-1 -a tru-prime
```

## 🎯 **Recommendation**

**For immediate testing:** Use Option 1 (Quick Fix)
**For production:** Use Option 2 (S3 Setup)

## ⚠️ **Current Deployment Status**

If you deploy the current quote system to Heroku without these fixes:

✅ **Will work:**
- Quote upload (file saves temporarily)
- GraphQL mutations/queries
- Database operations

❌ **Will fail:**
- PDF parsing (file access errors)
- OpenAI processing
- Quote completion

## 🚀 **Next Steps**

1. **Immediate:** Apply Option 1 quick fix
2. **This week:** Set up S3 with Option 2
3. **Test:** Upload a quote and verify parsing works
4. **Monitor:** Check Heroku logs for file access errors

Without these fixes, quote uploads will fail at the PDF parsing stage on Heroku!

