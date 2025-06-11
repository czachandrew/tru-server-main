# Amazon Search Functionality Implementation Summary

## Overview

This implementation adds Amazon search capability to the affiliate system, allowing the Puppeteer worker to search Amazon for products by part number or name, select the best match, and generate affiliate links automatically.

## Architecture

```
Django Backend          Redis Queue              Puppeteer Worker
     |                       |                        |
     |-- generate_affiliate  |                        |
     |   _url_from_search()  |                        |
     |                       |                        |
     |-- Publish message --> |-- 'affiliate_tasks' --|-- Process search
     |   to Redis channel    |   channel              |   task
     |                       |                        |
     |-- Store task data --> |-- pending_search_     |-- Search Amazon
     |   for tracking        |   task:{task_id}      |
     |                       |                        |
     |<-- Webhook callback --|<-- Send results -------|-- Generate 
     |   or Redis storage    |   via callback URL     |   affiliate link
```

## Implementation Components

### 1. Django Side (`affiliates/tasks.py`)

**New Functions Added:**

- `generate_affiliate_url_from_search(search_term, search_type='part_number')`
  - Creates and queues Amazon search tasks
  - Returns `(task_id, success_boolean)`
  - Supports search types: `'part_number'`, `'product_name'`, `'general'`

- `check_stalled_search_task(task_id, search_term)`
  - Safety check for stalled search tasks
  - Automatically scheduled 1 hour after task creation

**Message Format Sent to Redis:**
```json
{
  "taskType": "amazon_search",
  "searchTerm": "MX2Y3LL/A", 
  "searchType": "part_number",
  "taskId": "uuid-string",
  "callbackUrl": "http://localhost:8000/api/affiliate-search-callback/"
}
```

### 2. Puppeteer Side Implementation Needed

**Files to Modify:**
- Main worker file (your current puppeteer worker)

**Key Features to Add:**

1. **Message Type Detection**
   - Support both existing direct ASIN tasks and new search tasks
   - Route to appropriate handler based on `taskType`

2. **Amazon Search Engine**
   - Navigate to Amazon search results
   - Extract product data from first 15 results
   - Intelligent product scoring and selection

3. **Smart Product Selection**
   - Exact term matching (highest priority)
   - Part number recognition in titles/parentheses
   - Brand matching (Dell, Apple, HP, etc.)
   - Quality indicators (reviews, ratings, Prime status)

4. **Comprehensive Response**
   - Affiliate URL + detailed product metadata
   - Selection reasoning for debugging

## Message Differentiation in Redis Queue

### Current (Direct ASIN) Messages:
```json
{
  "asin": "B08N5WRWNW",
  "taskId": "uuid-string", 
  "callbackUrl": "webhook-url"
}
```
**Detected by:** Presence of `asin` field

### New (Search-based) Messages:
```json
{
  "taskType": "amazon_search",
  "searchTerm": "search-term",
  "searchType": "type",
  "taskId": "uuid-string",
  "callbackUrl": "webhook-url"
}
```
**Detected by:** `taskType: "amazon_search"`

### Worker Message Handler:
```javascript
subscriber.on("message", (channel, message) => {
  if (channel === "affiliate_tasks") {
    const taskData = JSON.parse(message);
    
    if (taskData.taskType === "amazon_search") {
      // Route to search handler
      cluster.queue(taskData);
    } else if (taskData.asin) {
      // Route to existing ASIN handler  
      cluster.queue({...taskData, taskType: "direct_asin"});
    }
  }
});
```

## Search Logic Flow

### 1. Amazon Search Process
```
Search Term → Amazon Search Results → Product Extraction → Scoring → Selection
```

### 2. Product Scoring Algorithm
- **Exact Match**: +100 points (search term found in title)
- **Part Number Match**: +80 points (for part_number search type)
- **Brand Match**: +40 points (same brand as search term)
- **Word Overlap**: +30 points (proportional to matched words)
- **Quality Score**: +15 points (based on reviews/ratings)
- **Prime Eligible**: +5 points
- **Position Bonus**: +15 points (earlier results favored)

### 3. Selection Criteria
- Minimum confidence threshold: 20 points
- Prioritizes exact matches over relevance scoring
- Logs top 3 candidates for debugging

## Testing

### Django Side Test Results ✅
```bash
python test_amazon_search.py
```
- ✅ Task queueing works correctly
- ✅ Redis message publishing confirmed
- ✅ Task tracking data stored properly
- ✅ All search types supported

### Puppeteer Side Testing Needed
1. **Part Number Search**: `"MX2Y3LL/A"` → Should find MacBook Pro
2. **Product Name Search**: `"Dell Latitude 5550"` → Should find Dell laptop  
3. **Generic Search**: `"laptop computer"` → Should find relevant laptop
4. **Backward Compatibility**: Existing ASIN tasks still work

## Integration Points

### 1. Chrome Extension Integration
The existing Chrome extension can use search functionality by calling:
```javascript
// Instead of direct ASIN
CreateAmazonAffiliateLink(asin: "B123456789", ...)

// New search-based approach  
CreateAmazonAffiliateFromSearch(searchTerm: "MX2Y3LL/A", searchType: "part_number", ...)
```

### 2. Consumer Matching Integration
The search results can feed into the existing consumer matching system:
```python
# In schema.py - enhance unifiedProductSearch
if not exact_product_found:
    # Use Amazon search as fallback
    task_id, success = generate_affiliate_url_from_search(search_term, 'part_number')
    # Return task_id to frontend for polling
```

### 3. Webhook Handling
Add new endpoint to handle search results:
```python
# In urls.py
path('api/affiliate-search-callback/', AffiliateSearchCallbackView.as_view())
```

## Expected Response Format

### Successful Search Response:
```json
{
  "affiliateUrl": "https://amzn.to/affiliate-link",
  "productData": {
    "asin": "B08N5WRWNW",
    "title": "Product Title",
    "price": "299.99",
    "image": "https://image-url.jpg",
    "rating": 4.5,
    "reviewCount": 1250,
    "isPrime": true,
    "searchTerm": "MX2Y3LL/A",
    "searchType": "part_number", 
    "selectionReason": "exact_term_match, prime_eligible"
  }
}
```

### Error Response:
```json
{
  "error": "No high-confidence product match found for 'xyz123'",
  "taskId": "uuid-string"
}
```

## Next Steps

1. **Implement Puppeteer Worker Changes**
   - Follow `PUPPETEER_SEARCH_IMPLEMENTATION_PROMPT.md`
   - Test with provided message formats
   - Ensure backward compatibility

2. **Add Webhook Endpoints**
   - Create `/api/affiliate-search-callback/` endpoint
   - Handle both success and error responses

3. **Integrate with Chrome Extension**
   - Add search-based affiliate link generation
   - Use as fallback when direct ASIN not available

4. **Monitor and Optimize**
   - Track search success rates
   - Refine scoring algorithm based on results
   - Add more sophisticated brand/model detection

## Benefits

- **Increased Coverage**: Find affiliate opportunities for any searchable product
- **Better Matching**: Intelligent product selection vs. manual ASIN lookup
- **Fallback Capability**: When direct ASINs aren't available
- **Future Scalability**: Foundation for advanced product discovery

The implementation maintains full backward compatibility while adding powerful new search capabilities to the affiliate system. 