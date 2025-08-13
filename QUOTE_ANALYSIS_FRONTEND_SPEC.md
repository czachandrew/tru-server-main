# Quote Analysis Frontend Integration Specification

## Overview
The Quote Analysis feature allows users to upload PDF quotes from resellers, automatically parse them using AI, and receive competitive pricing intelligence including affiliate product matches. This feature is designed to demonstrate pricing vulnerabilities to potential reseller partners.

## Core User Flow

### 1. Quote Upload
- **Drag & Drop Interface**: Users drag PDF files onto upload zone
- **File Validation**: Client-side validation for PDF files, max 10MB
- **Authentication Required**: Users must be logged in to upload quotes
- **Immediate Feedback**: Show upload progress and parsing status

### 2. Processing States
- **Uploading** → **Parsing** → **Matching** → **Completed**
- Real-time status updates via GraphQL subscriptions or polling
- Processing typically takes 10-30 seconds depending on PDF complexity

### 3. Results Display
- **Quote Overview**: Vendor info, totals, item count
- **Line Item Analysis**: Each product with competitive alternatives
- **Affiliate Matches**: Products available through affiliate programs (high impact for demos)
- **Savings Summary**: Total potential savings and competitive advantages

---

## GraphQL API Reference

### Upload Mutation

```graphql
mutation UploadQuote($file: Upload!, $demoMode: Boolean = false) {
  uploadQuote(file: $file, demoMode: $demoMode) {
    success
    message
    quote {
      id
      status
      originalFilename
      createdAt
    }
    errors
  }
}
```

**Parameters:**
- `file`: PDF file (max 10MB)
- `demoMode`: Enable demo pricing for unmatched products

**Response:**
- `success`: Boolean indicating upload success
- `message`: User-friendly status message
- `quote`: Basic quote information for tracking
- `errors`: Array of validation errors if any

### Quote Status Query

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
  }
}
```

**Status Values:**
- `uploading`: File is being uploaded
- `parsing`: AI is extracting data from PDF
- `matching`: Finding competitive products
- `completed`: Processing finished successfully
- `error`: Processing failed (check `parsingError`)

### Complete Quote Analysis Query

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
            sellingPrice
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

### User's Quote History

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
    # Savings summary
    potentialSavings
    affiliateOpportunities
  }
}
```

---

## Frontend Component Structure

### 1. QuoteUploader Component

```typescript
interface QuoteUploaderProps {
  onUploadSuccess: (quote: Quote) => void;
  onUploadError: (error: string) => void;
  demoMode?: boolean;
}

interface QuoteUploadState {
  isDragging: boolean;
  isUploading: boolean;
  uploadProgress?: number;
}
```

**Features:**
- Drag & drop zone with visual feedback
- File validation (PDF only, max 10MB)
- Upload progress indicator
- Error handling and user feedback

### 2. QuoteProcessor Component

```typescript
interface QuoteProcessorProps {
  quoteId: string;
  onProcessingComplete: (quote: QuoteAnalysis) => void;
}

interface ProcessingState {
  status: QuoteStatus;
  progress: number; // 0-100
  currentStep: string;
  estimatedTimeRemaining?: number;
}
```

**Features:**
- Real-time status updates
- Progress visualization
- Step-by-step feedback ("Parsing PDF...", "Finding matches...", etc.)
- Error handling with retry options

### 3. QuoteAnalysisResults Component

```typescript
interface QuoteAnalysisResultsProps {
  quote: QuoteAnalysis;
  showAffiliateOpportunities?: boolean;
  highlightSavings?: boolean;
}

interface QuoteAnalysisData {
  quote: Quote;
  totalSavings: number;
  savingsPercentage: number;
  affiliateOpportunities: number;
  competitiveThreats: CompetitiveThreat[];
}
```

**Features:**
- Executive summary with key metrics
- Detailed line-by-line analysis
- Affiliate opportunity highlights
- Savings calculator
- Export capabilities

---

## Key Data Models

### Quote Analysis Response
```typescript
interface QuoteAnalysis {
  id: string;
  status: 'uploading' | 'parsing' | 'matching' | 'completed' | 'error';
  vendorInfo: {
    name?: string;
    company?: string;
    quoteNumber?: string;
    quoteDate?: Date;
  };
  financials: {
    subtotal?: number;
    tax?: number;
    shipping?: number;
    total?: number;
  };
  items: QuoteItem[];
  summary: {
    totalItems: number;
    matchedItems: number;
    potentialSavings: number;
    savingsPercentage: number;
    affiliateOpportunities: number;
  };
}
```

### Quote Item with Competitive Analysis
```typescript
interface QuoteItem {
  id: string;
  lineNumber?: number;
  partNumber: string;
  description: string;
  manufacturer?: string;
  quantity: number;
  unitPrice: number;
  totalPrice: number;
  vendorSku?: string;
  extractionConfidence: number;
  
  // Competitive matches
  matches: ProductMatch[];
  
  // Analysis results
  bestAlternative?: ProductMatch;
  potentialSavings: number;
  savingsPercentage: number;
  hasAffiliateOption: boolean;
  competitiveRisk: 'HIGH' | 'MEDIUM' | 'LOW';
}
```

### Product Match
```typescript
interface ProductMatch {
  id: string;
  confidence: number;
  priceDifference: number;
  isExactMatch: boolean;
  matchMethod: 'exact_part_number' | 'fuzzy_match' | 'manufacturer_match' | 'description_similarity' | 'demo_generated';
  isDemoPrice: boolean;
  
  product?: {
    id: string;
    name: string;
    description: string;
    manufacturer: string;
    category: string;
    
    // Best available pricing
    bestOffer: {
      sellingPrice: number;
      vendor: string;
      vendorCode: string;
    };
    
    # Available affiliate links
    affiliateLinks: Array<{
      id: string;
      platform: string;
      affiliateUrl: string;
      commissionRate: number;
      isActive: boolean;
    }>;
  };
}
```

---

## UI/UX Recommendations

### 1. Upload Experience
- **Visual Design**: Modern drag & drop with animated upload states
- **Feedback**: Clear progress indicators and status messages
- **Error Handling**: Friendly error messages with suggested fixes
- **File Preview**: Show PDF thumbnail or filename before upload

### 2. Processing Experience
- **Progress Visualization**: Multi-step progress bar with current activity
- **Estimated Time**: Show estimated processing time (usually 10-30 seconds)
- **Background Processing**: Allow users to navigate away and return
- **Notifications**: Browser notifications when processing completes

### 3. Results Display

#### Executive Dashboard
```
┌─────────────────────────────────────────────────┐
│ Quote Analysis Summary                          │
├─────────────────────────────────────────────────┤
│ Vendor: CDW Technology Solutions                │
│ Quote #: Q12345678    Date: 2024-01-15         │
│ Total: $45,678.90     Items: 12                 │
├─────────────────────────────────────────────────┤
│ 💰 Potential Savings: $8,234 (18%)             │
│ 🔗 Affiliate Opportunities: 8 products         │
│ ⚠️  Competitive Risk: HIGH                      │
└─────────────────────────────────────────────────┘
```

#### Line Item Analysis
```
┌─────────────────────────────────────────────────┐
│ MacBook Pro 16" M2 Max                          │
│ Part: MX2Y3LL/A   Qty: 5   Price: $2,499 each  │
├─────────────────────────────────────────────────┤
│ ✅ Exact Match Found                            │
│ 🔗 Available via Amazon Affiliate: $2,299      │
│ 💰 Save: $200 each ($1,000 total)              │
│ ⚠️  Customer can buy directly for 8% less      │
└─────────────────────────────────────────────────┘
```

### 4. Demo Mode Features
- **Highlight Affiliate Opportunities**: Prominent badges for affiliate-available products
- **Risk Assessment**: Visual indicators for competitive threats
- **Savings Calculator**: Interactive savings visualization
- **Export Options**: PDF reports, CSV data export

---

## Real-time Updates

### WebSocket/Polling Strategy
```typescript
// Option 1: GraphQL Subscriptions (preferred)
subscription QuoteProcessingStatus($quoteId: ID!) {
  quoteProcessingStatus(quoteId: $quoteId) {
    status
    progress
    currentStep
    itemsProcessed
    estimatedTimeRemaining
  }
}

// Option 2: Polling fallback
const pollQuoteStatus = async (quoteId: string) => {
  const { data } = await client.query({
    query: QUOTE_STATUS_QUERY,
    variables: { id: quoteId },
    pollInterval: 2000, // Poll every 2 seconds
  });
  return data.quote;
};
```

---

## Error Handling

### Common Error Scenarios
1. **File Upload Errors**
   - File too large (>10MB)
   - Invalid file type (not PDF)
   - Network connection issues

2. **Processing Errors**
   - PDF parsing failures (corrupted/scanned files)
   - OpenAI API errors (rate limits, service issues)
   - Product matching timeouts

3. **Authentication Errors**
   - User not logged in
   - Session expired
   - Insufficient permissions

### Error Response Format
```typescript
interface ErrorResponse {
  success: false;
  message: string;
  errors: Array<{
    field?: string;
    code: string;
    message: string;
  }>;
  retryable: boolean;
}
```

---

## Performance Considerations

### 1. File Upload Optimization
- **Chunked Upload**: For large files, implement chunked upload
- **Client-side Compression**: Compress PDFs before upload if possible
- **Progress Tracking**: Accurate upload progress indicators

### 2. Processing Optimization
- **Background Jobs**: All heavy processing happens asynchronously
- **Caching**: OpenAI responses are cached to avoid duplicate processing
- **Batch Processing**: Multiple quotes can be processed simultaneously

### 3. Data Loading
- **Lazy Loading**: Load detailed analysis only when needed
- **Pagination**: For users with many quotes, implement pagination
- **Caching**: Cache processed results for quick re-access

---

## Security Considerations

### 1. File Upload Security
- **File Type Validation**: Server-side validation of PDF mime types
- **File Size Limits**: Enforce 10MB limit on both client and server
- **Virus Scanning**: Consider implementing virus scanning for uploaded files

### 2. Data Privacy
- **User Isolation**: Users can only access their own quotes
- **Data Retention**: Consider automatic cleanup of old quote files
- **Sensitive Data**: Handle vendor pricing information carefully

### 3. Rate Limiting
- **Upload Limits**: Limit number of uploads per user per hour
- **Processing Limits**: Prevent abuse of expensive OpenAI API calls
- **Authentication**: Require valid authentication for all operations

---

## Demo Strategy for Reseller Partners

### 1. Key Messaging Points
- **Competitive Vulnerability**: Show how easily customers can find better prices
- **Lost Revenue**: Quantify potential lost sales due to pricing gaps
- **Affiliate Competition**: Highlight direct-to-consumer alternatives
- **Market Intelligence**: Position as valuable competitive research tool

### 2. Demo Script Suggestions
1. **Upload Sample Quote**: Use real quote from potential partner
2. **Show Processing**: Demonstrate AI-powered analysis
3. **Reveal Results**: Focus on affiliate opportunities and savings
4. **Discuss Impact**: "Your customers can save 18% by shopping elsewhere"
5. **Position Solution**: How your platform can help them compete

### 3. Demo Data Setup
- Enable `demoMode` for consistent results
- Pre-populate with affiliate-heavy product matches
- Emphasize high-value, high-margin items
- Show realistic but compelling savings percentages

---

This specification provides everything needed to build a compelling frontend for the Quote Analysis feature, with special emphasis on demonstrating competitive risks to potential reseller partners.
