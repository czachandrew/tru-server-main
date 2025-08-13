# Quote Progress Polling & Lifecycle Guide

## 🔄 Complete Quote Upload & Processing Flow

### 1. Upload Quote (REST API)
```javascript
const uploadQuote = async (file, demoMode = false) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('demoMode', demoMode.toString());

  const response = await fetch('http://127.0.0.1:8000/upload-quote/', {
    method: 'POST',
    headers: {
      'Authorization': `JWT ${userToken}`,
    },
    body: formData
  });

  const result = await response.json();
  
  if (result.success) {
    // Start polling for progress immediately
    pollQuoteProgress(result.quote.id);
    return result.quote;
  } else {
    throw new Error(result.message);
  }
};
```

### 2. Poll for Progress (GraphQL)
```javascript
const pollQuoteProgress = async (quoteId) => {
  const POLL_INTERVAL = 2000; // 2 seconds
  const MAX_POLLS = 150; // 5 minutes max (150 * 2s = 300s)
  let pollCount = 0;

  const poll = async () => {
    try {
      const { data } = await apolloClient.query({
        query: QUOTE_STATUS_QUERY,
        variables: { id: quoteId },
        fetchPolicy: 'no-cache' // Always fetch fresh data
      });

      const quote = data.quote;
      
      // Update UI with current status
      updateQuoteProgress(quote);
      
      // Check if processing is complete
      if (quote.status === 'completed') {
        console.log('✅ Quote processing completed!');
        loadFullQuoteData(quoteId); // Load complete analysis
        return;
      }
      
      // Check for errors
      if (quote.status === 'error') {
        console.error('❌ Quote processing failed:', quote.parsingError);
        handleQuoteError(quote);
        return;
      }
      
      // Continue polling if still processing
      if (['uploading', 'parsing', 'matching'].includes(quote.status)) {
        pollCount++;
        if (pollCount < MAX_POLLS) {
          setTimeout(poll, POLL_INTERVAL);
        } else {
          console.warn('⏰ Polling timeout - quote may still be processing');
          handlePollingTimeout(quote);
        }
      }
      
    } catch (error) {
      console.error('Polling error:', error);
      // Retry with exponential backoff
      setTimeout(poll, POLL_INTERVAL * 2);
    }
  };

  // Start polling
  poll();
};
```

## 📊 Quote Status Lifecycle

### Status Progression
```
uploading → parsing → matching → completed
     ↓         ↓         ↓         ↓
   0-5s     5-30s    30-60s    Done!
```

### Status Meanings
- **`uploading`**: File is being uploaded (very brief)
- **`parsing`**: AI is extracting data from PDF (10-30 seconds)
- **`matching`**: Finding competitive products (10-30 seconds)  
- **`completed`**: Ready to display full analysis
- **`error`**: Processing failed (check `parsingError`)

## 🔍 GraphQL Queries

### Quote Status Query (For Polling)
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

### Full Quote Analysis (After Completion)
```graphql
query QuoteAnalysis($id: ID!) {
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
    originalFilename
    potentialSavings
    affiliateOpportunities
    itemCount
    matchedItemCount
    
    items {
      id
      lineNumber
      partNumber
      description
      manufacturer
      quantity
      unitPrice
      totalPrice
      extractionConfidence
      
      matches {
        id
        confidence
        priceDifference
        isExactMatch
        matchMethod
        isDemoPrice
        
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
          offers {
            sellingPrice
            vendor {
              name
              code
            }
          }
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

## 🎨 UI Implementation Guidelines

### 1. Upload State
```javascript
const [uploadState, setUploadState] = useState({
  isUploading: false,
  uploadProgress: 0,
  error: null
});

// Show upload progress
if (uploadState.isUploading) {
  return <UploadProgress progress={uploadState.uploadProgress} />;
}
```

### 2. Processing State
```javascript
const [processingQuotes, setProcessingQuotes] = useState(new Map());

const updateQuoteProgress = (quote) => {
  setProcessingQuotes(prev => new Map(prev.set(quote.id, {
    id: quote.id,
    status: quote.status,
    vendorCompany: quote.vendorCompany || 'Processing...',
    progress: getProgressPercentage(quote.status),
    itemCount: quote.itemCount || 0,
    matchedItemCount: quote.matchedItemCount || 0,
    error: quote.parsingError
  })));
};

const getProgressPercentage = (status) => {
  switch (status) {
    case 'uploading': return 10;
    case 'parsing': return 40;
    case 'matching': return 70;
    case 'completed': return 100;
    case 'error': return 0;
    default: return 0;
  }
};
```

### 3. Quote List Display
```javascript
const QuoteList = () => {
  const [completedQuotes, setCompletedQuotes] = useState([]);
  const [processingQuotes, setProcessingQuotes] = useState(new Map());

  return (
    <div>
      {/* Processing Quotes - Show Progress */}
      {Array.from(processingQuotes.values()).map(quote => (
        <QuoteProcessingCard 
          key={quote.id}
          quote={quote}
          progress={quote.progress}
          status={quote.status}
        />
      ))}
      
      {/* Completed Quotes - Show Full Data */}
      {completedQuotes.map(quote => (
        <QuoteAnalysisCard 
          key={quote.id}
          quote={quote}
          showSavings={true}
          showAffiliateThreats={true}
        />
      ))}
    </div>
  );
};
```

## ⚡ Performance Optimizations

### 1. Efficient Polling
```javascript
// Use different poll intervals based on status
const getPollInterval = (status) => {
  switch (status) {
    case 'uploading': return 1000; // 1 second - fast initial check
    case 'parsing': return 3000;   // 3 seconds - slower for AI processing
    case 'matching': return 2000;  // 2 seconds - moderate for matching
    default: return 5000;          // 5 seconds - fallback
  }
};
```

### 2. Smart Cache Management
```javascript
// Only fetch full data once processing is complete
const { data, loading } = useQuery(QUOTE_ANALYSIS_QUERY, {
  variables: { id: quoteId },
  skip: quote.status !== 'completed', // Don't query until ready
  fetchPolicy: 'cache-and-network'
});
```

### 3. Background Polling
```javascript
// Use React Query or SWR for automatic background updates
const useQuoteStatus = (quoteId, enabled = true) => {
  return useQuery(
    ['quote-status', quoteId],
    () => fetchQuoteStatus(quoteId),
    {
      enabled,
      refetchInterval: (data) => {
        if (!data || data.status === 'completed' || data.status === 'error') {
          return false; // Stop polling
        }
        return getPollInterval(data.status);
      }
    }
  );
};
```

## 🚨 Error Handling

### 1. Processing Errors
```javascript
const handleQuoteError = (quote) => {
  console.error(`Quote ${quote.id} failed:`, quote.parsingError);
  
  // Remove from processing list
  setProcessingQuotes(prev => {
    const newMap = new Map(prev);
    newMap.delete(quote.id);
    return newMap;
  });
  
  // Show error to user
  showErrorNotification({
    title: 'Quote Processing Failed',
    message: quote.parsingError || 'An unknown error occurred',
    action: 'Try uploading again'
  });
};
```

### 2. Network Errors
```javascript
const handleNetworkError = (error, quoteId) => {
  console.warn('Network error during polling:', error);
  
  // Implement exponential backoff
  const retryDelay = Math.min(1000 * Math.pow(2, retryCount), 30000);
  setTimeout(() => pollQuoteProgress(quoteId), retryDelay);
};
```

## 🎯 User Experience Best Practices

### 1. Progress Visualization
```javascript
const QuoteProcessingCard = ({ quote, progress, status }) => (
  <div className="quote-processing-card">
    <div className="header">
      <h3>{quote.vendorCompany}</h3>
      <span className="status-badge">{status}</span>
    </div>
    
    <div className="progress-bar">
      <div className="progress-fill" style={{ width: `${progress}%` }} />
    </div>
    
    <div className="details">
      <span>📄 {quote.itemCount} items found</span>
      <span>🔍 {quote.matchedItemCount} matched</span>
    </div>
    
    <div className="status-message">
      {getStatusMessage(status)}
    </div>
  </div>
);

const getStatusMessage = (status) => {
  switch (status) {
    case 'parsing': return 'AI is reading your PDF...';
    case 'matching': return 'Finding competitive prices...';
    case 'completed': return 'Analysis complete!';
    default: return 'Processing...';
  }
};
```

### 2. Prevent Showing Incomplete Data
```javascript
// DON'T show quotes in main list until completed
const shouldShowInList = (quote) => {
  return quote.status === 'completed' && quote.itemCount > 0;
};

// Filter quotes for display
const displayQuotes = allQuotes.filter(shouldShowInList);
```

### 3. Loading States
```javascript
const QuoteAnalysisView = ({ quoteId }) => {
  const { data: quote, loading } = useQuery(QUOTE_STATUS_QUERY, {
    variables: { id: quoteId }
  });

  if (loading) return <LoadingSpinner />;
  
  if (quote.status !== 'completed') {
    return <QuoteProcessingView quote={quote} />;
  }
  
  return <QuoteAnalysisResults quote={quote} />;
};
```

## 🔄 Complete Implementation Example

```javascript
const useQuoteWorkflow = () => {
  const [processingQuotes, setProcessingQuotes] = useState(new Map());
  const [completedQuotes, setCompletedQuotes] = useState([]);

  const uploadQuote = async (file, demoMode = false) => {
    try {
      const result = await uploadQuoteToAPI(file, demoMode);
      
      if (result.success) {
        // Add to processing list
        setProcessingQuotes(prev => new Map(prev.set(result.quote.id, {
          ...result.quote,
          progress: 10
        })));
        
        // Start polling
        pollQuoteProgress(result.quote.id);
        
        return result.quote;
      }
    } catch (error) {
      console.error('Upload failed:', error);
      throw error;
    }
  };

  const pollQuoteProgress = async (quoteId) => {
    // Implementation from above...
  };

  const onQuoteCompleted = (quote) => {
    // Remove from processing
    setProcessingQuotes(prev => {
      const newMap = new Map(prev);
      newMap.delete(quote.id);
      return newMap;
    });
    
    // Add to completed list
    setCompletedQuotes(prev => [quote, ...prev]);
    
    // Show success notification
    showSuccessNotification({
      title: 'Quote Analysis Complete!',
      message: `Found ${quote.affiliateOpportunities} competitive threats`
    });
  };

  return {
    uploadQuote,
    processingQuotes: Array.from(processingQuotes.values()),
    completedQuotes
  };
};
```

## 🎉 Summary

**Key Points for Frontend Team:**

1. **Upload via REST** → **Poll via GraphQL** → **Display when complete**
2. **Never show quotes until `status === 'completed'`**
3. **Poll every 2-3 seconds during processing**
4. **Stop polling when complete or error**
5. **Handle network errors with retries**
6. **Show progress visualization during processing**
7. **Use `fetchPolicy: 'no-cache'` for status polling**
8. **Load full analysis data only after completion**

This approach ensures users see smooth progress updates and only complete, accurate quote data! 🚀
