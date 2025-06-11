# Amazon Search Functionality Implementation for Puppeteer Worker

## Context & Current System

You are working with a Node.js Puppeteer worker that currently handles Amazon affiliate link generation for **direct ASINs**. The system receives tasks via Redis pub/sub and processes them to generate affiliate links using Amazon's SiteStripe tool.

**Current Redis Message Format:**
```json
{
  "asin": "B08N5WRWNW",
  "taskId": "uuid-string",
  "callbackUrl": "https://example.com/webhook"
}
```

**Current Task Flow:**
1. Receive ASIN → Navigate to product page → Generate affiliate link → Return result

## New Requirement: Amazon Search + Affiliate Link Generation

Add functionality to search Amazon using a search term (part number, product name, etc.), select the best matching product from search results, and then generate an affiliate link for that product.

## Enhanced Redis Message Format

The worker should support **two message types**:

### Type 1: Direct ASIN (existing - no changes)
```json
{
  "taskType": "direct_asin",
  "asin": "B08N5WRWNW", 
  "taskId": "uuid-string",
  "callbackUrl": "https://example.com/webhook"
}
```

### Type 2: Search-based (new functionality)
```json
{
  "taskType": "amazon_search",
  "searchTerm": "MX2Y3LL/A",
  "searchType": "part_number",
  "taskId": "uuid-string", 
  "callbackUrl": "https://example.com/webhook"
}
```

**Search Types:**
- `"part_number"` - Exact part number matching (e.g., "MX2Y3LL/A", "VFR3R")
- `"product_name"` - Product name matching (e.g., "Dell Latitude 5550")
- `"general"` - General search term

## Implementation Requirements

### 1. Message Processing Enhancement

Modify the Redis message handler to detect and route different task types:

```javascript
subscriber.on("message", (channel, message) => {
  if (channel === "affiliate_tasks") {
    try {
      const taskData = JSON.parse(message);
      
      // Determine task type - support backward compatibility
      if (taskData.taskType === "amazon_search") {
        console.log(`📥 Search Task: ${taskData.searchTerm} (${taskData.searchType})`);
        cluster.queue(taskData);
      } else if (taskData.asin || taskData.taskType === "direct_asin") {
        console.log(`📥 Direct ASIN Task: ${taskData.asin}`);
        cluster.queue({...taskData, taskType: "direct_asin"});
      } else {
        console.error("❌ Unknown task type:", taskData);
      }
    } catch (e) {
      console.error("❌ Error parsing message:", e);
    }
  }
});
```

### 2. Task Router Implementation

Enhance the cluster task handler to route between direct ASIN and search tasks:

```javascript
await cluster.task(async ({ page, data }) => {
  const { taskType, taskId } = data;
  
  try {
    if (taskType === "amazon_search") {
      return await processAmazonSearchTask(page, data);
    } else {
      return await processDirectASINTask(page, data); // existing logic
    }
  } catch (error) {
    console.error(`❌ Task ${taskId} failed:`, error.message);
    await handleTaskError(data, error);
    throw error;
  }
});
```

### 3. Amazon Search Implementation

Create the core search functionality:

```javascript
async function processAmazonSearchTask(page, { searchTerm, searchType, taskId, callbackUrl }) {
  console.log(`🔍 Amazon Search Task: "${searchTerm}" (type: ${searchType})`);
  
  try {
    // Step 1: Perform Amazon search
    const searchResults = await performAmazonSearch(page, searchTerm);
    
    if (searchResults.length === 0) {
      throw new Error(`No Amazon search results found for: ${searchTerm}`);
    }
    
    // Step 2: Select best product using intelligent matching
    const selectedProduct = selectBestProduct(searchResults, searchTerm, searchType);
    console.log(`🎯 Selected: ${selectedProduct.title} (ASIN: ${selectedProduct.asin})`);
    
    // Step 3: Generate affiliate link using existing SiteStripe logic
    const affiliateUrl = await generateAffiliateLink(page, selectedProduct.asin);
    
    // Step 4: Prepare comprehensive response
    const response = {
      affiliateUrl: affiliateUrl,
      productData: {
        asin: selectedProduct.asin,
        title: selectedProduct.title,
        price: selectedProduct.price,
        image: selectedProduct.image,
        rating: selectedProduct.rating,
        reviewCount: selectedProduct.reviewCount,
        isPrime: selectedProduct.isPrime,
        searchTerm: searchTerm,
        searchType: searchType,
        selectionReason: selectedProduct.selectionReason
      }
    };
    
    // Step 5: Send response
    await sendTaskResponse(callbackUrl, taskId, response);
    return response;
    
  } catch (error) {
    console.error(`❌ Search task failed for "${searchTerm}":`, error.message);
    await sendTaskError(callbackUrl, taskId, error.message);
    throw error;
  }
}
```

### 4. Amazon Search Logic

```javascript
async function performAmazonSearch(page, searchTerm) {
  console.log(`🔍 Searching Amazon for: "${searchTerm}"`);
  
  // Navigate to Amazon search
  const searchUrl = `https://www.amazon.com/s?k=${encodeURIComponent(searchTerm)}&ref=sr_pg_1`;
  await page.goto(searchUrl, { waitUntil: "networkidle2", timeout: 30000 });
  
  // Extract search results from first page
  const searchResults = await page.evaluate((searchTerm) => {
    const results = [];
    const productElements = document.querySelectorAll('[data-component-type="s-search-result"]');
    
    productElements.forEach((element, index) => {
      if (index >= 15) return; // Limit to first 15 results
      
      try {
        // Extract ASIN (required)
        const asin = element.getAttribute('data-asin');
        if (!asin || asin === '') return;
        
        // Extract title
        const titleElement = element.querySelector('h2 a span') || 
                           element.querySelector('[data-cy="title-recipe-title"] span');
        const title = titleElement ? titleElement.textContent.trim() : '';
        if (!title) return;
        
        // Extract price
        const priceWhole = element.querySelector('.a-price-whole');
        const priceFraction = element.querySelector('.a-price-fraction');
        let price = '';
        if (priceWhole) {
          price = priceWhole.textContent + (priceFraction ? '.' + priceFraction.textContent : '');
        }
        
        // Extract rating
        const ratingElement = element.querySelector('.a-icon-alt');
        const ratingMatch = ratingElement ? ratingElement.textContent.match(/(\d+\.?\d*) out of/) : null;
        const rating = ratingMatch ? parseFloat(ratingMatch[1]) : 0;
        
        // Extract review count  
        const reviewElement = element.querySelector('a[href*="#customerReviews"] span') ||
                            element.querySelector('.a-size-base');
        let reviewCount = 0;
        if (reviewElement) {
          const reviewText = reviewElement.textContent.replace(/[,()]/g, '');
          const reviewMatch = reviewText.match(/(\d+)/);
          reviewCount = reviewMatch ? parseInt(reviewMatch[1]) : 0;
        }
        
        // Extract image
        const imageElement = element.querySelector('img[data-image-latency]') || 
                           element.querySelector('.s-image');
        const image = imageElement ? imageElement.src : '';
        
        // Check for Prime
        const isPrime = !!element.querySelector('[aria-label*="Prime"]') ||
                       !!element.querySelector('.a-icon-prime');
        
        // Store position for tie-breaking
        const position = index + 1;
        
        results.push({
          asin,
          title,
          price,
          image,
          rating,
          reviewCount,
          isPrime,
          position
        });
        
      } catch (error) {
        console.log(`Error extracting product ${index}:`, error.message);
      }
    });
    
    console.log(`Extracted ${results.length} search results`);
    return results;
  }, searchTerm);
  
  return searchResults;
}
```

### 5. Intelligent Product Selection

```javascript
function selectBestProduct(searchResults, searchTerm, searchType) {
  console.log(`🎯 Selecting best product from ${searchResults.length} results`);
  
  // Score each product
  const scoredResults = searchResults.map(product => {
    const score = calculateProductScore(product, searchTerm, searchType);
    return { ...product, score, selectionReason: score.reason };
  });
  
  // Sort by score (highest first)
  scoredResults.sort((a, b) => b.score.total - a.score.total);
  
  // Log top 3 candidates
  console.log("🏆 Top candidates:");
  scoredResults.slice(0, 3).forEach((product, i) => {
    console.log(`  ${i+1}. ${product.title.substring(0, 60)}... (Score: ${product.score.total})`);
  });
  
  const winner = scoredResults[0];
  if (winner.score.total < 20) {
    throw new Error(`No high-confidence product match found for "${searchTerm}"`);
  }
  
  console.log(`✅ Selected: ${winner.title.substring(0, 80)}... (Score: ${winner.score.total})`);
  return winner;
}

function calculateProductScore(product, searchTerm, searchType) {
  let score = 0;
  let reasons = [];
  
  const titleLower = product.title.toLowerCase();
  const searchLower = searchTerm.toLowerCase();
  
  // EXACT MATCHING (highest priority)
  if (titleLower.includes(searchLower)) {
    score += 100;
    reasons.push("exact_term_match");
  }
  
  // PART NUMBER SPECIFIC SCORING
  if (searchType === "part_number") {
    // Look for part number in title or parentheses
    const partNumberRegex = new RegExp(searchTerm.replace(/[-\s]/g, '[-\\s]?'), 'i');
    if (partNumberRegex.test(product.title)) {
      score += 80;
      reasons.push("part_number_match");
    }
    
    // Check for part number in parentheses (common Amazon format)
    const parenMatch = product.title.match(/\(([^)]+)\)/);
    if (parenMatch && parenMatch[1].toLowerCase().includes(searchLower)) {
      score += 60;
      reasons.push("parentheses_match");
    }
  }
  
  // BRAND MATCHING
  const brands = ['Dell', 'Apple', 'HP', 'Lenovo', 'Microsoft', 'ASUS', 'Acer', 'Samsung'];
  const searchBrand = brands.find(brand => searchLower.includes(brand.toLowerCase()));
  const titleBrand = brands.find(brand => titleLower.includes(brand.toLowerCase()));
  
  if (searchBrand && titleBrand && searchBrand.toLowerCase() === titleBrand.toLowerCase()) {
    score += 40;
    reasons.push("brand_match");
  }
  
  // WORD OVERLAP SCORING
  const searchWords = searchLower.split(/\s+/).filter(word => word.length > 2);
  const titleWords = titleLower.split(/\s+/);
  const matchedWords = searchWords.filter(word => 
    titleWords.some(titleWord => titleWord.includes(word) || word.includes(titleWord))
  );
  
  if (searchWords.length > 0) {
    const wordScore = (matchedWords.length / searchWords.length) * 30;
    score += wordScore;
    if (wordScore > 15) reasons.push("high_word_overlap");
  }
  
  // QUALITY INDICATORS
  score += Math.min(product.reviewCount / 100, 15); // Max 15 points
  score += product.rating * 3; // Max 15 points  
  if (product.isPrime) {
    score += 5;
    reasons.push("prime_eligible");
  }
  
  // POSITION BONUS (earlier results slightly favored)
  score += Math.max(16 - product.position, 0); // Max 15 points
  
  return {
    total: Math.round(score),
    reason: reasons.join(", ") || "general_relevance"
  };
}
```

### 6. Affiliate Link Generation (Reuse Existing)

Extract your existing SiteStripe logic into a reusable function:

```javascript
async function generateAffiliateLink(page, asin) {
  console.log(`🔗 Generating affiliate link for ASIN: ${asin}`);
  
  // Navigate to product page
  const productUrl = `https://www.amazon.com/dp/${asin}`;
  await page.goto(productUrl, { waitUntil: "networkidle2", timeout: 30000 });
  
  // Check login status and handle if needed
  const isLoggedIn = await checkLoginStatus(page);
  if (!isLoggedIn) {
    console.log("🔑 Not logged in, performing login...");
    await performLogin(page);
    await page.goto(productUrl, { waitUntil: "networkidle2", timeout: 30000 });
  }
  
  // Check for SiteStripe
  const hasSiteStripe = await page.evaluate(() => {
    return !!document.querySelector('#amzn-ss-text-link');
  });
  
  if (!hasSiteStripe) {
    console.log("⚠️ SiteStripe not found, refreshing session...");
    await page.goto("https://affiliate-program.amazon.com/home", { waitUntil: "networkidle2" });
    await page.goto(productUrl, { waitUntil: "networkidle2" });
  }
  
  // Generate link using SiteStripe
  await page.waitForSelector('#amzn-ss-text-link', { timeout: 15000 });
  await page.click('#amzn-ss-text-link');
  await page.waitForSelector('#amzn-ss-text-shortlink-textarea', { timeout: 15000 });
  
  const affiliateLink = await page.$eval('#amzn-ss-text-shortlink-textarea', el => el.value);
  console.log(`✅ Generated affiliate link: ${affiliateLink}`);
  
  return affiliateLink;
}
```

### 7. Response Handling

```javascript
async function sendTaskResponse(callbackUrl, taskId, responseData) {
  if (callbackUrl) {
    try {
      const response = await axios.post(callbackUrl, responseData, {
        timeout: 10000,
        headers: { 'Content-Type': 'application/json' }
      });
      console.log(`✅ Webhook success for task ${taskId}`);
    } catch (error) {
      console.error(`❌ Webhook failed for task ${taskId}:`, error.message);
      // Fallback to Redis
      await redis.set(`affiliate_result:${taskId}`, JSON.stringify(responseData), "EX", 3600);
    }
  } else {
    // Store in Redis
    await redis.set(`affiliate_result:${taskId}`, JSON.stringify(responseData), "EX", 3600);
  }
}

async function sendTaskError(callbackUrl, taskId, errorMessage) {
  const errorData = { error: errorMessage, taskId };
  
  if (callbackUrl) {
    try {
      await axios.post(callbackUrl, errorData);
    } catch (webhookError) {
      await redis.set(`affiliate_result:${taskId}`, JSON.stringify(errorData), "EX", 3600);
    }
  } else {
    await redis.set(`affiliate_result:${taskId}`, JSON.stringify(errorData), "EX", 3600);
  }
}
```

## Testing Requirements

Test the implementation with these scenarios:

1. **Part Number Search**: `{"taskType": "amazon_search", "searchTerm": "MX2Y3LL/A", "searchType": "part_number"}`
2. **Product Name Search**: `{"taskType": "amazon_search", "searchTerm": "Dell Latitude 5550", "searchType": "product_name"}`  
3. **Generic Search**: `{"taskType": "amazon_search", "searchTerm": "laptop computer", "searchType": "general"}`
4. **Backward Compatibility**: `{"asin": "B08N5WRWNW"}` (should still work)

## Error Handling Requirements

- Graceful handling of no search results
- Fallback when no high-confidence matches found
- Comprehensive logging for debugging
- Proper error reporting via webhook/Redis

## Performance Considerations

- Limit search results to first 15 products
- Implement reasonable timeouts
- Cache login session across tasks
- Take screenshots on errors for debugging

Implement this functionality while maintaining full backward compatibility with the existing direct ASIN processing system. 