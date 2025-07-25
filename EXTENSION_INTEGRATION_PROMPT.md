# Extension Integration: Affiliate Click Tracking & Purchase Intent Detection

## Overview

This document outlines the complete implementation requirements for integrating affiliate click tracking and purchase intent detection into the browser extension. The goal is to provide real-time feedback to users about their projected earnings from affiliate activities.

## Architecture Overview

```
User clicks affiliate link → Extension tracks click → User shops → Extension detects checkout → Backend creates projected earnings → User sees projected balance
```

## Core Principles

### 1. **Accurate Tracking**
- Track every affiliate link click with complete context
- Correlate checkout activity with original affiliate links
- Provide detailed product matching for commission calculations

### 2. **Progressive Confidence Building**
- Start with basic click tracking (30% confidence)
- Increase confidence as user progresses through checkout stages
- Only create projected earnings for medium+ confidence events

### 3. **Privacy-First Design**
- Collect only necessary data for commission tracking
- Respect user privacy settings
- Provide clear opt-out mechanisms

### 4. **Performance Optimization**
- Lightweight content script injection
- Efficient DOM parsing and monitoring
- Minimal impact on user browsing experience

## Implementation Requirements

### Phase 1: Affiliate Click Tracking

#### 1.1 Click Detection
When a user clicks an affiliate link from your platform:

```javascript
// Background script
function trackAffiliateClick(affiliateLink) {
    const clickData = {
        affiliate_link_id: affiliateLink.id,
        session_id: generateSessionId(),
        target_domain: extractDomain(affiliateLink.url),
        referrer_url: window.location.href,
        source: 'extension',
        product_data: {
            name: affiliateLink.product.name,
            price: affiliateLink.product.price,
            category: affiliateLink.product.category,
            platform: affiliateLink.platform
        },
        browser_fingerprint: generateBrowserFingerprint()
    };
    
    // Send to backend using GraphQL
    // Convert to camelCase for GraphQL
    const graphqlInput = {
        affiliateLinkId: clickData.affiliate_link_id,
        sessionId: clickData.session_id,
        targetDomain: clickData.target_domain,
        referrerUrl: clickData.referrer_url,
        source: clickData.source,
        productData: JSON.stringify(clickData.product_data),
        browserFingerprint: clickData.browser_fingerprint
    };

    const query = `
        mutation TrackAffiliateClick($input: TrackAffiliateClickInput!) {
            trackAffiliateClick(input: $input) {
                success
                clickEventId
                message
            }
        }
    `;
    
    fetch('/graphql/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `JWT ${userToken}`
        },
        body: JSON.stringify({
            query: query,
            variables: { input: graphqlInput }
        })
    });
}
```

#### 1.2 Session Monitoring
Track user activity on the target merchant site:

```javascript
// Content script injected on merchant sites
class SessionMonitor {
    constructor(clickEventId) {
        this.clickEventId = clickEventId;
        this.startTime = Date.now();
        this.isActive = true;
        
        this.setupEventListeners();
        this.startHeartbeat();
    }
    
    setupEventListeners() {
        // Track page visibility
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.reportSessionEnd();
            }
        });
        
        // Track page unload
        window.addEventListener('beforeunload', () => {
            this.reportSessionEnd();
        });
    }
    
    reportSessionEnd() {
        if (!this.isActive) return;
        
        const duration = Math.floor((Date.now() - this.startTime) / 1000);
        
        const query = `
            mutation UpdateSessionDuration($input: UpdateSessionDurationInput!) {
                updateSessionDuration(input: $input) {
                    success
                    message
                }
            }
        `;
        
        fetch('/graphql/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `JWT ${userToken}`
            },
            body: JSON.stringify({
                query: query,
                variables: {
                    input: {
                        clickEventId: this.clickEventId,  // camelCase
                        durationSeconds: duration         // camelCase
                    }
                }
            })
        });
        
        this.isActive = false;
    }
}
```

### Phase 2: Purchase Intent Detection

#### 2.1 Purchase Intent Reporting
When checkout stage is detected:

```javascript
class PurchaseIntentReporter {
    constructor(clickEventId) {
        this.clickEventId = clickEventId;
    }
    
    reportPurchaseIntent(stage, cartAnalysis) {
        const confidenceLevel = this.calculateConfidenceLevel(stage, cartAnalysis);
        
        const query = `
            mutation TrackPurchaseIntent($input: TrackPurchaseIntentInput!) {
                trackPurchaseIntent(input: $input) {
                    success
                    intentEventId
                    created
                    message
                    projectedEarning {
                        transactionId
                        amount
                        confidenceLevel
                        userBalance
                    }
                }
            }
        `;
        
        const variables = {
            input: {
                clickEventId: this.clickEventId,                    // camelCase
                intentStage: stage,                                 // camelCase
                confidenceLevel: confidenceLevel,                  // camelCase
                pageUrl: window.location.href,                     // camelCase
                pageTitle: document.title,                         // camelCase
                cartTotal: cartAnalysis.cartTotal,                 // camelCase
                cartItems: JSON.stringify(cartAnalysis.cartItems), // camelCase
                matchedProducts: JSON.stringify(cartAnalysis.matchedProducts) // camelCase
            }
        };
        
        fetch('/graphql/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `JWT ${userToken}`
            },
            body: JSON.stringify({
                query: query,
                variables: variables
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.data?.trackPurchaseIntent?.projectedEarning) {
                // User has projected earnings!
                this.notifyUser(data.data.trackPurchaseIntent.projectedEarning);
            }
        });
    }
    
    calculateConfidenceLevel(stage, cartAnalysis) {
        const stageConfidence = {
            'cart_add': 'LOW',
            'cart_view': 'LOW',
            'shipping_info': 'MEDIUM',
            'payment_page': 'HIGH',
            'payment_info': 'HIGH',
            'order_review': 'VERY_HIGH',
            'order_submit': 'VERY_HIGH',
            'order_confirmed': 'VERY_HIGH'
        };
        
        let confidence = stageConfidence[stage] || 'LOW';
        
        // Boost confidence if products match
        if (cartAnalysis.matchedProducts.length > 0) {
            const confidenceBoost = {
                'LOW': 'MEDIUM',
                'MEDIUM': 'HIGH',
                'HIGH': 'VERY_HIGH',
                'VERY_HIGH': 'VERY_HIGH'
            };
            confidence = confidenceBoost[confidence];
        }
        
        return confidence;
    }
}
```

### Phase 3: User Activity Monitoring

#### 3.1 Get User Activity
Retrieve user's affiliate activity and projected earnings:

```javascript
async function getUserAffiliateActivity() {
    const query = `
        query GetUserAffiliateActivity {
            userAffiliateActivity {
                recentClicks {
                    id
                    affiliateLink {
                        id
                        platform
                        product {
                            name
                        }
                    }
                    clickedAt
                    targetDomain
                    sessionDuration
                    hasPurchaseIntent
                }
                projectedEarnings {
                    id
                    amount
                    createdAt
                    confidenceLevel
                    intentStage
                    platform
                }
                walletSummary {
                    availableBalance
                    pendingBalance
                    totalBalance
                }
            }
        }
    `;
    
    const response = await fetch('/graphql/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `JWT ${userToken}`
        },
        body: JSON.stringify({ query })
    });
    
    const data = await response.json();
    return data.data?.userAffiliateActivity;
}
```

// ... rest of the existing content remains the same with these key changes:

### Phase 4: GraphQL Integration

#### 4.1 Available GraphQL Operations

**Mutations:**
- `trackAffiliateClick(input: TrackAffiliateClickInput!)`: Track affiliate link clicks
- `trackPurchaseIntent(input: TrackPurchaseIntentInput!)`: Track purchase intent
- `updateSessionDuration(input: UpdateSessionDurationInput!)`: Update session duration

**Queries:**
- `userAffiliateActivity`: Get user's recent activity and projected earnings

#### 4.2 GraphQL Field Name Mapping

**IMPORTANT**: GraphQL uses camelCase, not snake_case. Use these field names:

**TrackAffiliateClickInput:**
- `affiliateLinkId` (not affiliate_link_id)
- `sessionId` (not session_id)
- `targetDomain` (not target_domain)
- `referrerUrl` (not referrer_url)
- `productData` (not product_data)
- `browserFingerprint` (not browser_fingerprint)

**TrackPurchaseIntentInput:**
- `clickEventId` (not click_event_id)
- `intentStage` (not intent_stage)
- `confidenceLevel` (not confidence_level)
- `pageUrl` (not page_url)
- `pageTitle` (not page_title)
- `cartTotal` (not cart_total)
- `cartItems` (not cart_items)
- `matchedProducts` (not matched_products)

**UpdateSessionDurationInput:**
- `clickEventId` (not click_event_id)
- `durationSeconds` (not duration_seconds)

#### 4.3 Authentication
All GraphQL operations require JWT authentication:
```javascript
headers: {
    'Authorization': `JWT ${userToken}`
}
```

#### 4.4 Error Handling
GraphQL errors are returned in the response:
```javascript
fetch('/graphql/', { /* ... */ })
    .then(response => response.json())
    .then(data => {
        if (data.errors) {
            console.error('GraphQL errors:', data.errors);
            // Handle errors appropriately
        } else {
            // Handle successful response
            console.log('Success:', data.data);
        }
    });
```

### Phase 5: Real-Time Updates

#### 5.1 Polling for Updates
Since we're using GraphQL, you can poll for updates:

```javascript
class WalletMonitor {
    constructor() {
        this.pollInterval = 30000; // 30 seconds
        this.isPolling = false;
    }
    
    startPolling() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        this.poll();
    }
    
    async poll() {
        try {
            const activity = await getUserAffiliateActivity();
            this.updateUI(activity);
        } catch (error) {
            console.error('Error polling activity:', error);
        }
        
        if (this.isPolling) {
            setTimeout(() => this.poll(), this.pollInterval);
        }
    }
    
    updateUI(activity) {
        // Update extension popup with latest earnings
        const walletSummary = activity.walletSummary;
        document.getElementById('pending-balance').textContent = 
            `$${walletSummary.pendingBalance.toFixed(2)}`;
        document.getElementById('available-balance').textContent = 
            `$${walletSummary.availableBalance.toFixed(2)}`;
    }
}
```

This GraphQL-based approach provides:
- **Type Safety**: GraphQL schema ensures correct data types
- **Single Endpoint**: All operations through `/graphql/`
- **Consistent Authentication**: JWT tokens for all operations
- **Better Error Handling**: Structured error responses
- **Introspection**: GraphQL schema is self-documenting

The extension team can use GraphQL introspection to explore the available operations and their parameters, making integration more reliable and maintainable.

### Phase 7: GraphQL Error Handling

#### 7.1 GraphQL Error Handling
```javascript
class GraphQLErrorHandler {
    static handleGraphQLResponse(response) {
        return response.json().then(data => {
            if (data.errors) {
                // Handle GraphQL errors
                data.errors.forEach(error => {
                    console.error('GraphQL Error:', error.message);
                    
                    // Handle specific error types
                    if (error.message.includes('Authentication required')) {
                        this.handleAuthError();
                    } else if (error.message.includes('not found')) {
                        this.handleNotFoundError(error);
                    } else {
                        this.handleGenericError(error);
                    }
                });
                
                throw new Error('GraphQL operation failed');
            }
            
            return data.data;
        });
    }
    
    static handleAuthError() {
        // Redirect to login or refresh token
        console.log('Authentication error - redirecting to login');
        // Implement token refresh logic
    }
    
    static handleNotFoundError(error) {
        console.log('Resource not found:', error.message);
        // Handle missing resources gracefully
    }
    
    static handleGenericError(error) {
        console.error('GraphQL error:', error.message);
        // Store for retry or user notification
    }
}
```

#### 7.2 Retry Logic for GraphQL Operations
```javascript
class GraphQLRetryHandler {
    static async executeWithRetry(operation, maxRetries = 3) {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                const response = await fetch('/graphql/', operation);
                return await GraphQLErrorHandler.handleGraphQLResponse(response);
            } catch (error) {
                if (attempt === maxRetries) {
                    throw error;
                }
                
                // Exponential backoff
                const delay = Math.pow(2, attempt) * 1000;
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }
}
```

### Phase 8: Testing & Validation

#### 8.1 GraphQL Testing
```javascript
// Test GraphQL mutations
async function testAffiliateTracking() {
    const testClickData = {
        affiliate_link_id: "123",
        session_id: "test-session",
        target_domain: "amazon.com",
        source: "extension"
    };
    
    try {
        const result = await GraphQLRetryHandler.executeWithRetry({
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `JWT ${testToken}`
            },
            body: JSON.stringify({
                query: `
                    mutation TrackAffiliateClick($input: TrackAffiliateClickInput!) {
                        trackAffiliateClick(input: $input) {
                            success
                            clickEventId
                            message
                        }
                    }
                `,
                variables: { input: testClickData }
            })
        });
        
        console.log('Click tracking test passed:', result);
    } catch (error) {
        console.error('Click tracking test failed:', error);
    }
}
```

#### 8.2 Test Scenarios
1. **GraphQL Click Tracking**: Test the `trackAffiliateClick` mutation
2. **GraphQL Purchase Intent**: Test the `trackPurchaseIntent` mutation
3. **GraphQL Session Updates**: Test the `updateSessionDuration` mutation
4. **GraphQL Activity Query**: Test the `userAffiliateActivity` query
5. **Authentication**: Test JWT token handling
6. **Error Handling**: Test GraphQL error responses

### Phase 9: Performance Optimization

#### 9.1 GraphQL Query Optimization
```javascript
// Optimize GraphQL queries by requesting only needed fields
const optimizedQuery = `
    query GetUserAffiliateActivity {
        userAffiliateActivity {
            walletSummary {
                pendingBalance
                availableBalance
            }
            projectedEarnings(first: 5) {
                amount
                confidenceLevel
            }
        }
    }
`;
```

#### 9.2 Batching GraphQL Operations
```javascript
// Batch multiple operations in a single request
const batchedQuery = `
    mutation BatchedTracking(
        $clickInput: TrackAffiliateClickInput!
        $intentInput: TrackPurchaseIntentInput!
    ) {
        trackAffiliateClick(input: $clickInput) {
            success
            clickEventId
        }
        trackPurchaseIntent(input: $intentInput) {
            success
            projectedEarning {
                amount
            }
        }
    }
`;
```

## Security Considerations

1. **JWT Token Management**: Securely store and refresh JWT tokens
2. **GraphQL Security**: Validate all GraphQL variables and inputs
3. **Privacy Controls**: Respect user privacy settings
4. **Query Depth Limiting**: Prevent overly complex GraphQL queries

## Performance Metrics

Track these GraphQL-specific metrics:
- GraphQL query/mutation success rates
- Average GraphQL response times
- Token refresh frequency
- Extension impact on page load times
- User conversion rates

## Deployment Checklist

- [ ] Implement GraphQL mutations for tracking
- [ ] Add GraphQL error handling and retry logic
- [ ] Test GraphQL operations across merchant sites
- [ ] Validate JWT authentication flow
- [ ] Performance testing with GraphQL
- [ ] Security audit for GraphQL endpoints
- [ ] User acceptance testing

## Support & Troubleshooting

For GraphQL integration issues:
1. Check browser console for GraphQL errors
2. Verify GraphQL endpoint accessibility (`/graphql/`)
3. Confirm JWT token validity and format
4. Test GraphQL operations using GraphiQL interface
5. Monitor network requests for failed GraphQL calls
6. Use GraphQL introspection to explore available operations

This comprehensive GraphQL-based integration provides users with real-time feedback on their affiliate earnings while maintaining consistency with your existing API architecture. 