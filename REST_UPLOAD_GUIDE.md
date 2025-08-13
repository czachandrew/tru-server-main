# REST Quote Upload API Guide

## 🎯 Solution Overview

Your frontend team is absolutely right! GraphQL file uploads can be complex with modern build tools like Vite. The REST endpoint provides a simple, reliable solution that works with standard HTTP multipart uploads.

## 📡 REST Endpoint

**URL:** `http://127.0.0.1:8000/upload-quote/`  
**Method:** `POST`  
**Content-Type:** `multipart/form-data`  
**Authentication:** JWT token in Authorization header

## 🔐 Authentication

Include JWT token in the Authorization header:
```
Authorization: JWT <your-jwt-token>
```

## 📤 Request Format

### Form Data Fields:
- **`file`** (required): The PDF file to upload
- **`demoMode`** (optional): `"true"` or `"false"` (default: `"false"`)

### Example JavaScript/Fetch:
```javascript
const uploadQuote = async (file, demoMode = false, jwtToken) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('demoMode', demoMode.toString());

  const response = await fetch('http://127.0.0.1:8000/upload-quote/', {
    method: 'POST',
    headers: {
      'Authorization': `JWT ${jwtToken}`,
    },
    body: formData
  });

  return await response.json();
};
```

### Example cURL:
```bash
curl -X POST http://127.0.0.1:8000/upload-quote/ \
  -H "Authorization: JWT your-jwt-token-here" \
  -F "file=@sample-quote.pdf" \
  -F "demoMode=true"
```

## 📥 Response Format

The REST endpoint returns the **exact same format** as the GraphQL mutation:

### Success Response (201):
```json
{
  "success": true,
  "message": "Quote uploaded successfully and processing started",
  "quote": {
    "id": "123",
    "status": "parsing",
    "originalFilename": "sample-quote.pdf",
    "createdAt": "2024-01-15T10:30:00.000Z",
    "demoModeEnabled": true
  },
  "errors": []
}
```

### Error Response (400/401/500):
```json
{
  "success": false,
  "message": "Error description",
  "quote": null,
  "errors": ["Specific error details"]
}
```

## 🚫 Validation Rules

The REST endpoint performs the same validations as GraphQL:

1. **File Required**: Must include `file` in form data
2. **PDF Only**: File must have `.pdf` extension and `application/pdf` MIME type
3. **Size Limit**: Maximum 10MB file size
4. **Authentication**: Valid JWT token required
5. **User Exists**: Token must reference existing user

## 🔄 Processing Flow

1. **Upload** → Status: `"uploading"`
2. **Validation** → File type, size, auth checks
3. **Queue Processing** → Status: `"parsing"`
4. **Background Task** → AI parsing and product matching
5. **Completion** → Status: `"completed"` or `"error"`

## 🎯 Frontend Integration

Your frontend components **don't need to change**! The REST endpoint:

- ✅ Uses standard FormData (no special GraphQL packages)
- ✅ Works with all modern browsers and build tools
- ✅ Returns same data format as GraphQL
- ✅ Handles authentication the same way
- ✅ Provides identical error handling

## 📊 Status Checking

After upload, use the existing GraphQL queries to check processing status:

```graphql
query QuoteStatus($id: ID!) {
  quote(id: $id) {
    id
    status
    vendorCompany
    total
    itemCount
    potentialSavings
    affiliateOpportunities
  }
}
```

## 🚀 Benefits vs GraphQL Upload

| Feature | REST Upload | GraphQL Upload |
|---------|-------------|----------------|
| **Build Tool Compatibility** | ✅ Universal | ❌ Can have issues |
| **Package Dependencies** | ✅ None needed | ❌ Special packages required |
| **Browser Support** | ✅ All browsers | ❌ May need polyfills |
| **Implementation Complexity** | ✅ Simple | ❌ Complex |
| **File Size Handling** | ✅ Native support | ❌ Chunking complexity |
| **Error Handling** | ✅ Standard HTTP | ❌ GraphQL-specific |

## 🔧 Testing

Test the endpoint with a sample PDF:

```bash
# Get a JWT token first (via login mutation)
# Then test upload:
curl -X POST http://127.0.0.1:8000/upload-quote/ \
  -H "Authorization: JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -F "file=@sample-quote.pdf" \
  -F "demoMode=true"
```

Expected response:
```json
{
  "success": true,
  "message": "Quote uploaded successfully and processing started",
  "quote": {
    "id": "8",
    "status": "parsing"
  }
}
```

## 💡 Why This Approach Wins

Your frontend team identified the core issue: **GraphQL file uploads are unnecessarily complex for simple file operations**. This REST approach:

1. **Reduces Complexity**: No special GraphQL upload packages
2. **Improves Reliability**: Standard HTTP multipart uploads always work
3. **Maintains Consistency**: Same auth, same response format, same data flow
4. **Future-Proof**: Works with any frontend framework or build tool

## 🔧 CORS Configuration Fixed

✅ **CORS headers now properly configured** for the REST endpoint:
- Removed URL restriction that limited CORS to GraphQL only
- Added proper headers for file uploads (`content-type`, `authorization`, etc.)
- Enabled all necessary HTTP methods (`POST`, `OPTIONS`, etc.)
- Supports preflight requests for cross-origin uploads

## 🐛 Debugging JWT Authentication

If you're getting 401 Unauthorized errors, use the debug endpoint to test your JWT token:

**Debug Endpoint:** `http://127.0.0.1:8000/test-jwt/`

```javascript
// Test your JWT token
fetch('http://127.0.0.1:8000/test-jwt/', {
  method: 'POST',
  headers: {
    'Authorization': `JWT ${yourToken}`,
  }
});
```

This will return detailed information about token validation issues.

## 🔧 Common JWT Issues

1. **Token format**: Must be `JWT <token>`, not `Bearer <token>`
2. **Token source**: Ensure token comes from GraphQL login mutation
3. **Token expiry**: Tokens expire after 60 minutes
4. **Header casing**: Use `Authorization` (capital A)

The REST endpoint is now live and ready for your team to use! 🎉
