# Quote Analysis - Corrected GraphQL Query

## ❌ Frontend Error Fix

The frontend team got schema validation errors because my initial spec didn't match the actual backend schema. Here's the corrected query:

## ✅ Corrected GraphQL Query

```graphql
query QuoteAnalysis($id: ID!) {
  quote(id: $id) {
    # Basic quote info
    id
    status
    vendorName
    vendorCompany
    quoteNumber
    quoteDate
    subtotal
    tax
    shipping
    total
    originalFilename
    parsingError
    
    # Line items with competitive analysis
    items {
      id
      lineNumber
      partNumber
      description
      manufacturer
      quantity
      unitPrice
      totalPrice
      vendorSku
      extractionConfidence
      
      # Competitive matches
      matches {
        id
        confidence
        priceDifference
        isExactMatch
        matchMethod
        isDemoPrice
        
        # Matched product details
        product {
          id
          name
          description
          manufacturer {
            name
          }
          categories {
            name
          }
          # Current best price from our system  
          offers {
            id
            sellingPrice
            offerType
            isConfirmed
            sourceQuote {
              id
              quoteNumber
            }
            vendor {
              name
              code
            }
          }
          # Affiliate links for direct-to-consumer alternatives
          affiliateLinks {
            id
            platform
            affiliateUrl
            commissionRate
            isActive
          }
        }
      }
    }
  }
}
```

## 🔧 Key Changes Made

### 1. Product Schema Fixes
- ❌ `category` → ✅ `categories` (it's a list, not singular)
- ❌ `price` on Offer → ✅ `sellingPrice` 
- ❌ `affiliateLink` on Offer → ✅ `affiliateLinks` on Product
- ❌ `slug` on Vendor → ✅ `code`

### 2. Schema Structure
The actual backend has:
- **Product.categories**: Array of categories (not singular)
- **Offer.sellingPrice**: The actual selling price field
- **Product.affiliateLinks**: Separate relationship for affiliate links
- **Vendor.code**: Used instead of slug for vendor identification

## 🎯 Working Example

This query will now work correctly and return data like:

```json
{
  "data": {
    "quote": {
      "id": "8",
      "status": "completed",
      "vendorCompany": "CDW Technology Solutions",
      "total": "45678.90",
      "items": [
        {
          "partNumber": "DS1621XS+",
          "description": "NAS server - 6 bays",
          "unitPrice": "1445.85",
          "matches": [
            {
              "confidence": 0.95,
              "priceDifference": "-200.00",
              "product": {
                "name": "Synology DS1621XS+",
                "categories": [
                  { "name": "Network Storage" }
                ],
                "offers": [
                  {
                    "sellingPrice": "1245.85",
                    "vendor": {
                      "name": "Amazon",
                      "code": "AMZN"
                    }
                  }
                ],
                "affiliateLinks": [
                  {
                    "platform": "amazon",
                    "affiliateUrl": "https://amzn.to/...",
                    "commissionRate": "4.00",
                    "isActive": true
                  }
                ]
              }
            }
          ]
        }
      ]
    }
  }
}
```

## 💡 Frontend Team Action Required

Please update your GraphQL query to use the corrected field names above. The main changes are:
1. `category` → `categories`
2. `price` → `sellingPrice` 
3. Move `affiliateLink` from `offers` to `product.affiliateLinks`
4. Use `vendor.code` instead of `vendor.slug`

This will resolve all the schema validation errors you're seeing.

## ✅ Additional Corrected Queries

### My Quotes List Query
```graphql
query MyQuotes {
  myQuotes {
    id
    vendorCompany
    quoteNumber
    total
    status
    itemCount
    matchedItemCount
    createdAt
    # Computed savings analysis (now available!)
    potentialSavings
    affiliateOpportunities
  }
}
```

Note: I just added the `potentialSavings` and `affiliateOpportunities` computed fields to the backend, so these queries will now work!

### Quote Status Query (For Polling Progress)
```graphql
query QuoteStatus($id: ID!) {
  quote(id: $id) {
    id
    status
    vendorName
    vendorCompany
    quoteNumber
    quoteDate
    subtotal
    tax
    shipping
    total
    itemCount
    matchedItemCount
    createdAt
    updatedAt
    processedAt
    parsingError
    estimatedTimeRemaining
  }
}
```

**Key Fields:**
- `status`: Current processing status (`"uploading"`, `"parsing"`, `"matching"`, `"completed"`, `"error"`)
- `parsingError`: Error message if processing failed (null if successful)
- `itemCount`: Total number of line items found
- `matchedItemCount`: Number of items with product matches
- `estimatedTimeRemaining`: Seconds remaining until completion (null when completed/error)

## 🚨 **CRITICAL: Proper Polling Workflow**

### ❌ **DON'T DO THIS** (Common Mistakes)
```javascript
// DON'T show quotes immediately after upload
const quotes = useQuery(MY_QUOTES_QUERY); // Shows empty data

// DON'T poll too frequently
setInterval(checkStatus, 500); // Too fast, wastes resources

// DON'T show incomplete quotes in lists
{allQuotes.map(quote => <QuoteCard />)} // Shows parsing quotes
```

### ✅ **DO THIS** (Correct Implementation)
```javascript
// 1. Upload → Get quote ID → Start polling
const uploadResult = await uploadQuote(file);
pollQuoteProgress(uploadResult.quote.id);

// 2. Poll every 2-3 seconds with no-cache
const { data } = useQuery(QUOTE_STATUS_QUERY, {
  variables: { id: quoteId },
  fetchPolicy: 'no-cache',
  pollInterval: 2000
});

// 3. Only show quotes when status === 'completed'
const displayQuotes = quotes.filter(q => q.status === 'completed');

// 4. Stop polling when done
if (quote.status === 'completed' || quote.status === 'error') {
  stopPolling();
}
```

### 📋 **Status Lifecycle**
```
Upload → uploading → parsing → matching → completed
  1s       2-5s      10-30s     10-30s     DONE!
```

**🎯 See `QUOTE_PROGRESS_POLLING_GUIDE.md` for complete implementation details!**
