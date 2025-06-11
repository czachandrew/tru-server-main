# Product Association System

## Overview

The Product Association System creates intelligent relationships between products to optimize future searches and reduce redundant Amazon API calls. When a user searches for "Dell keyboard" and we find a "Logitech MX Keys" on Amazon, we remember this relationship for future efficiency.

## Key Benefits

- **🚀 Faster Searches**: Skip redundant Amazon searches when we already have good alternatives
- **💰 Cost Optimization**: Reduce Amazon API calls as the system scales to 100s of requests per minute  
- **🎯 Better UX**: Instantly return known alternatives instead of waiting for Amazon search
- **📊 Intelligence**: Build understanding of what alternatives work well for different searches

## How It Works

### 1. Association Creation
When the Chrome extension finds an Amazon product via search:
- We capture the original search term (e.g., "Dell XPS keyboard")
- We identify the Amazon product found (e.g., "Logitech MX Keys")
- We create a `ProductAssociation` linking them with metadata

### 2. Search Intelligence
Before making new Amazon searches:
- Check `get_existing_associations(search_term)` for known alternatives
- If high-quality associations exist (confidence ≥ 0.7, search_count ≥ 2), skip Amazon
- Return existing alternatives instantly

### 3. Performance Tracking
Each association tracks:
- `search_count`: How often this association was reinforced
- `click_count`: How often users clicked this alternative
- `conversion_count`: How often this led to purchases
- `confidence_score`: Algorithm confidence in this association

## Database Schema

```sql
-- Key fields in ProductAssociation model
CREATE TABLE affiliates_productassociation (
    id BIGINT PRIMARY KEY,
    source_product_id BIGINT NULL,           -- Original product searched for
    target_product_id BIGINT NOT NULL,       -- Alternative found
    original_search_term VARCHAR(255),       -- "Dell XPS keyboard"
    association_type VARCHAR(30),            -- 'cross_brand_alternative', etc.
    confidence_score DECIMAL(3,2),           -- 0.00-1.00
    search_count INTEGER DEFAULT 1,          -- Reinforcement counter
    click_count INTEGER DEFAULT 0,           -- User engagement
    conversion_count INTEGER DEFAULT 0,      -- Purchase success
    created_via_platform VARCHAR(50),        -- 'amazon'
    search_context JSONB,                    -- Additional metadata
    is_active BOOLEAN DEFAULT TRUE,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP
);
```

## Usage Examples

### GraphQL Queries

```graphql
# Check for existing alternatives before Amazon search
query CheckAlternatives {
  existingAlternatives(searchTerm: "Dell XPS keyboard") {
    id
    targetProduct {
      name
      partNumber
      affiliateLinks {
        affiliateUrl
      }
    }
    searchCount
    confidenceScore
    clickThroughRate
    conversionRate
  }
}

# Get all associations for analytics
query GetAssociations {
  productAssociations(limit: 100) {
    originalSearchTerm
    associationType
    searchCount
    confidenceScore
    targetProduct {
      name
      manufacturer {
        name
      }
    }
  }
}
```

### Python Usage

```python
from affiliates.views import get_existing_associations, should_skip_amazon_search

# Check for existing alternatives
alternatives = get_existing_associations("Dell keyboard")
if alternatives:
    print(f"Found {len(alternatives)} known alternatives")

# Determine if we should skip Amazon search
should_skip, high_quality = should_skip_amazon_search("Dell XPS keyboard")
if should_skip:
    print("Using cached alternatives instead of Amazon search")
    return high_quality
```

## Association Types

- `search_alternative`: Found when searching for original
- `same_brand_alternative`: Same manufacturer  
- `cross_brand_alternative`: Different manufacturer
- `upgrade_option`: Better/newer version
- `budget_option`: Cheaper alternative
- `compatible_accessory`: Works with original
- `bundle_item`: Often bought together

## Performance Metrics

### Click-Through Rate (CTR)
```python
ctr = (click_count / search_count) * 100
```

### Conversion Rate  
```python
conversion_rate = (conversion_count / click_count) * 100
```

### Confidence Score Factors
- Exact brand match: +0.2
- Price similarity: +0.1  
- Category match: +0.1
- User engagement: +0.1-0.3
- Search reinforcement: +0.05 per occurrence

## Integration Points

### Chrome Extension
The extension can check for existing alternatives before triggering Amazon searches:

```javascript
// Before Amazon search
const alternatives = await checkExistingAlternatives(searchTerm);
if (alternatives.length > 0 && alternatives[0].confidenceScore > 0.7) {
    return alternatives; // Skip Amazon API call
}
```

### Admin Interface
Monitor associations via Django admin:
- View search patterns and popular alternatives
- Identify high-performing cross-brand substitutions  
- Track conversion rates by association type
- Disable low-quality associations

## Future Enhancements

1. **Machine Learning**: Use association data to predict better alternatives
2. **Price Tracking**: Monitor price changes in associated products
3. **Seasonal Intelligence**: Different associations for holiday vs normal periods
4. **Category-Specific Logic**: Keyboards vs monitors might have different association rules
5. **Bulk Operations**: Pre-populate associations from historical search data

## Monitoring

Key metrics to track:
- Association hit rate (% of searches that find existing alternatives)
- Amazon API call reduction (before/after implementation)
- User satisfaction with suggested alternatives
- Revenue impact from faster vs Amazon searches

This system creates a self-improving intelligence layer that gets smarter with every search, dramatically improving performance as scale increases. 