# Extension Click Tracking Implementation

## 🎯 **CRITICAL ISSUE IDENTIFIED**

The extension is currently calling `trackPurchaseIntent` without first calling `trackAffiliateClick`. This causes the backend to fail finding the click event, preventing projected earnings from being created and wallet balances from updating.

## 🔄 **REQUIRED IMPLEMENTATION FLOW**

### **Step 1: Detect Affiliate Arrival**
When a user arrives on a page via an affiliate link (detected by URL parameters, referrer, or stored session data):

```javascript
// 1. Generate consistent session ID
const sessionId = `affiliate_arrival_${Date.now()}`;

// 2. Track the affiliate click IMMEDIATELY
const clickMutation = `
  mutation TrackAffiliateClick($input: TrackAffiliateClickInput!) {
    trackAffiliateClick(input: $input) {
      success
      clickEvent {
        id
        sessionId
        affiliateLink {
          platform
          product {
            name
          }
        }
      }
      message
    }
  }
`;

const clickVariables = {
  input: {
    sessionId: sessionId,
    affiliateLinkId: detectedAffiliateLinkId, // Extract from URL/context
    targetDomain: window.location.hostname,
    productData: {
      // Extract product info from page
      name: extractProductName(),
      price: extractProductPrice(),
      sku: extractProductSku(),
      // ... other product details
    }
  }
};

// Execute the click tracking
const clickResult = await makeGraphQLRequest(clickMutation, clickVariables);

if (clickResult.data?.trackAffiliateClick?.success) {
  // Store session ID for later use
  sessionStorage.setItem('affiliateSessionId', sessionId);
  console.log('✅ Affiliate click tracked successfully');
} else {
  console.error('❌ Failed to track affiliate click:', clickResult);
}
```

### **Step 2: Track Purchase Intent (Only After Click is Tracked)**
When purchase intent is detected (cart page, checkout page, etc.):

```javascript
// 1. Retrieve the session ID from earlier click tracking
const sessionId = sessionStorage.getItem('affiliateSessionId');

if (!sessionId) {
  console.warn('⚠️ No affiliate session found - user did not arrive via tracked affiliate link');
  return; // Don't track purchase intent without affiliate click
}

// 2. Track purchase intent using the SAME session ID
const intentMutation = `
  mutation TrackPurchaseIntent($input: TrackPurchaseIntentInput!) {
    trackPurchaseIntent(input: $input) {
      success
      projectedEarning {
        transactionId
        amount
        confidenceLevel
        userBalance
      }
      message
    }
  }
`;

const intentVariables = {
  input: {
    clickEventId: sessionId, // Use session ID, not database ID
    intentStage: "payment_page", // or cart_view, order_review, etc.
    confidenceLevel: "HIGH", // HIGH/MEDIUM/VERY_HIGH for wallet updates
    confidenceScore: 0.85,
    cartTotal: extractCartTotal(),
    cartItems: extractCartItems(),
    matchedProducts: matchProductsFromCart(),
    pageUrl: window.location.href
  }
};

// Execute purchase intent tracking
const intentResult = await makeGraphQLRequest(intentMutation, intentVariables);

if (intentResult.data?.trackPurchaseIntent?.success) {
  console.log('✅ Purchase intent tracked - projected earning created');
  console.log('💰 Projected amount:', intentResult.data.trackPurchaseIntent.projectedEarning.amount);
} else {
  console.error('❌ Failed to track purchase intent:', intentResult);
}
```

## 🔧 **KEY IMPLEMENTATION REQUIREMENTS**

### **1. Session Management**
```javascript
// Store affiliate session data
const affiliateSession = {
  sessionId: sessionId,
  affiliateLinkId: affiliateLinkId,
  platform: detectedPlatform,
  arrivalTime: Date.now(),
  tracked: false
};

sessionStorage.setItem('affiliateSession', JSON.stringify(affiliateSession));
```

### **2. Affiliate Link Detection**
Implement robust detection for:
- URL parameters (`ref=`, `tag=`, `aff_id=`, etc.)
- Referrer analysis
- Platform-specific patterns (Amazon Associates, etc.)

### **3. Product Data Extraction**
Extract comprehensive product information:
```javascript
function extractProductData() {
  return {
    name: document.querySelector('h1')?.textContent || extractFromMeta('product:name'),
    price: extractPriceFromPage(),
    sku: extractFromMeta('product:sku') || extractFromURL(),
    brand: extractFromMeta('product:brand'),
    category: extractCategoryFromBreadcrumbs(),
    images: extractProductImages(),
    description: extractProductDescription()
  };
}
```

### **4. Cart Analysis**
For purchase intent detection:
```javascript
function extractCartItems() {
  // Platform-specific cart item extraction
  return Array.from(document.querySelectorAll('.cart-item')).map(item => ({
    name: item.querySelector('.item-name')?.textContent,
    price: parseFloat(item.querySelector('.item-price')?.textContent.replace(/[^0-9.]/g, '')),
    quantity: parseInt(item.querySelector('.item-quantity')?.textContent),
    sku: item.dataset.sku || extractSkuFromItem(item)
  }));
}
```

### **5. Confidence Level Logic**
```javascript
function calculateConfidenceLevel(pageType, cartTotal, userBehavior) {
  if (pageType === 'order_confirmed') return 'VERY_HIGH';
  if (pageType === 'payment_info' && cartTotal > 0) return 'HIGH';
  if (pageType === 'payment_page') return 'HIGH';
  if (pageType === 'cart_view' && cartTotal > 50) return 'MEDIUM';
  return 'LOW';
}
```

## 🎯 **CRITICAL SUCCESS CRITERIA**

1. **✅ ALWAYS call `trackAffiliateClick` FIRST** when user arrives via affiliate link
2. **✅ Use consistent `sessionId`** between click tracking and purchase intent
3. **✅ Only track purchase intent if affiliate click was tracked**
4. **✅ Use confidence levels MEDIUM/HIGH/VERY_HIGH** for wallet updates
5. **✅ Extract accurate cart totals and product matches**

## 🔄 **TESTING VERIFICATION**

After implementation, verify:
1. Navigate to affiliate link → Check backend logs for successful click tracking
2. Add to cart → Check backend logs for purchase intent tracking
3. Check wallet balance updates in extension popup
4. Verify projected earnings appear in user affiliate activity

## 📋 **BACKEND EXPECTATIONS**

The backend is correctly configured and will:
- ✅ Create `AffiliateClickEvent` from `trackAffiliateClick`
- ✅ Find click event by `sessionId` in `trackPurchaseIntent`
- ✅ Create projected earnings for MEDIUM+ confidence levels
- ✅ Update user `pending_balance` immediately
- ✅ Return projected earning data to extension

**The wallet update logic is working correctly** - it just needs the proper click tracking sequence to trigger it! 🎯 