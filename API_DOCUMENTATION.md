# TruPrice Ecommerce Platform - GraphQL API Documentation

## Overview

The TruPrice Ecommerce Platform provides a comprehensive GraphQL API for building ecommerce websites with intelligent product search, price comparison, and affiliate link integration. The platform specializes in finding the best deals across multiple vendors and generating affiliate revenue through Amazon partnerships.

**GraphQL Endpoint:** `http://your-domain.com/graphql/`

## Core Concepts

### Product Types
- **Primary Products**: Direct supplier inventory with competitive pricing
- **Amazon Products**: Products sourced from Amazon with affiliate links
- **Alternative Products**: Similar products when exact matches aren't available
- **Future Opportunity Products**: Products tracked for future sourcing

### Revenue Models
- **Supplier Sales**: Direct product sales with markup
- **Affiliate Commissions**: Revenue from Amazon affiliate links
- **Cross-sell Opportunities**: Related product recommendations

## Authentication

Most queries are public, but user-specific features require authentication:

```graphql
query {
  me {
    id
    email
    firstName
    lastName
    wallet
  }
}
```

## Core Queries

### 1. Product Search (Primary API)

The unified product search is the main entry point for finding products:

```graphql
query UnifiedSearch($asin: String, $partNumber: String, $name: String) {
  unifiedProductSearch(asin: $asin, partNumber: $partNumber, name: $name) {
    id
    name
    partNumber
    mainImage
    description
    manufacturer {
      name
    }
    price
    asin
    isAmazonProduct
    isAlternative
    relationshipType      # "primary", "equivalent", "accessory", "cross_sell"
    relationshipCategory  # "exact_match", "intelligent_name_match", "same_brand_alternative"
    marginOpportunity     # "high", "medium", "low", "affiliate_only"
    revenueType          # "product_sale", "affiliate_commission", "cross_sell_opportunity"
    matchType            # "exact_part_number", "intelligent_name_match", "amazon_search_pending"
    matchConfidence      # 0.0 to 1.0 confidence score
    affiliateLinks {
      id
      platform
      affiliateUrl
    }
    offers {
      id
      productName
      sellingPrice
      vendor {
        name
      }
      offerType           # "supplier" or "affiliate"
      commissionRate
      isInStock
      stockQuantity
    }
  }
}
```

**Usage Examples:**

```graphql
# Search by Amazon ASIN
query { unifiedProductSearch(asin: "B08N5WRWNW") { ... } }

# Search by manufacturer part number
query { unifiedProductSearch(partNumber: "MXK53AM/A") { ... } }

# Search by product name
query { unifiedProductSearch(name: "Apple Magic Mouse") { ... } }

# Combined search (most accurate)
query { 
  unifiedProductSearch(
    asin: "B08N5WRWNW", 
    partNumber: "MXK53AM/A", 
    name: "Apple Magic Mouse"
  ) { ... } 
}
```

### 2. Consumer Product Search

For general product discovery:

```graphql
query ConsumerSearch($searchTerm: String!, $limit: Int) {
  consumerProductSearch(searchTerm: $searchTerm, limit: $limit) {
    id
    name
    title                 # Amazon-style product title
    price
    currency
    availability
    productUrl
    imageUrl
    asin
    affiliateLinks {
      platform
      affiliateUrl
    }
    offers {
      sellingPrice
      vendor {
        name
        isAffiliate
      }
      isInStock
    }
  }
}
```

### 3. Product Details

Get detailed information about a specific product:

```graphql
query ProductDetails($id: ID!) {
  product(id: $id) {
    id
    name
    description
    partNumber
    mainImage
    manufacturer {
      name
      website
    }
    categories {
      name
      slug
    }
    specifications
    weight
    dimensions
    status
    affiliateLinks {
      platform
      affiliateUrl
      commissionRate
    }
    offers {
      id
      sellingPrice
      costPrice
      msrp
      vendor {
        name
        website
        isAffiliate
      }
      vendorSku
      vendorUrl
      stockQuantity
      isInStock
      offerType
      commissionRate
    }
  }
}
```

### 4. Price Comparison

Get all available offers for a product:

```graphql
query PriceComparison($productId: ID!) {
  priceComparison(
    productId: $productId
    includeAffiliate: true
    includeSupplier: true
  ) {
    id
    sellingPrice
    offerType
    commissionAmount
    vendor {
      name
      isAffiliate
    }
  }
}
```

### 5. Featured Products

Get featured products for homepage:

```graphql
query FeaturedProducts($limit: Int) {
  featuredProducts(limit: $limit) {
    id
    name
    mainImage
    manufacturer {
      name
    }
    offers {
      sellingPrice
      vendor {
        name
      }
    }
    affiliateLinks {
      platform
      affiliateUrl
    }
  }
}
```

### 6. Categories & Navigation

```graphql
query Categories {
  categories {
    id
    name
    slug
    description
    parent {
      name
    }
  }
}

query CategoryProducts($categoryId: ID!, $limit: Int, $offset: Int) {
  products(categoryId: $categoryId, limit: $limit, offset: $offset) {
    totalCount
    items {
      id
      name
      mainImage
      offers {
        sellingPrice
      }
    }
  }
}
```

## Shopping Cart & Checkout

### 1. Cart Management

```graphql
# Get or create cart
query GetCart($sessionId: String) {
  cart(sessionId: $sessionId) {
    id
    items {
      id
      quantity
      offer {
        product {
          name
          mainImage
        }
        sellingPrice
        vendor {
          name
        }
      }
    }
    totalAmount
  }
}

# Add to cart
mutation AddToCart($sessionId: String, $item: CartItemInput!) {
  addToCart(sessionId: $sessionId, item: $item) {
    id
    totalAmount
    items {
      id
      quantity
      offer {
        sellingPrice
      }
    }
  }
}

# Update quantity
mutation UpdateCartItem($id: ID!, $quantity: Int!) {
  updateCartItem(id: $id, quantity: $quantity) {
    id
    quantity
  }
}

# Remove item
mutation RemoveFromCart($id: ID!) {
  removeFromCart(id: $id)
}
```

## Key Response Fields Explained

### Product Relationship Types
- **`primary`**: Exact product match with direct sales opportunity
- **`equivalent`**: Similar product that serves the same purpose
- **`accessory`**: Compatible accessories or add-ons
- **`cross_sell`**: Related products for upselling

### Match Types
- **`exact_part_number`**: Perfect part number match
- **`intelligent_name_match`**: AI-matched based on product name similarity
- **`same_brand_alternative`**: Same manufacturer, different model
- **`amazon_search_pending`**: Amazon search in progress
- **`amazon_search_result`**: Found via Amazon API

### Revenue Indicators
- **`marginOpportunity`**: Profit potential (high/medium/low/affiliate_only)
- **`revenueType`**: How money is made (product_sale/affiliate_commission/cross_sell_opportunity)

## Building an Ecommerce Website

### 1. Homepage Implementation

```javascript
// Featured products carousel
const FEATURED_PRODUCTS_QUERY = `
  query FeaturedProducts {
    featuredProducts(limit: 12) {
      id
      name
      mainImage
      manufacturer { name }
      offers {
        sellingPrice
        vendor { name }
      }
      affiliateLinks {
        platform
        affiliateUrl
      }
    }
  }
`;
```

### 2. Search Results Page

```javascript
// Universal search with intelligent alternatives
const SEARCH_QUERY = `
  query Search($term: String!) {
    unifiedProductSearch(name: $term) {
      id
      name
      mainImage
      relationshipType
      matchType
      matchConfidence
      offers {
        sellingPrice
        vendor { name }
        isInStock
      }
      affiliateLinks {
        affiliateUrl
      }
    }
  }
`;

// Display logic
function renderSearchResults(results) {
  const exactMatches = results.filter(p => p.matchType === 'exact_part_number');
  const alternatives = results.filter(p => p.relationshipType === 'equivalent');
  const accessories = results.filter(p => p.relationshipType === 'accessory');
  
  return {
    exactMatches,    // Show first
    alternatives,    // Show as "Similar Products"
    accessories      // Show as "Compatible Accessories"
  };
}
```

### 3. Product Detail Page

```javascript
const PRODUCT_DETAIL_QUERY = `
  query ProductDetail($id: ID!) {
    product(id: $id) {
      id
      name
      description
      mainImage
      specifications
      offers {
        id
        sellingPrice
        vendor { name }
        isInStock
        stockQuantity
        offerType
      }
      affiliateLinks {
        platform
        affiliateUrl
      }
    }
  }
`;

// Price comparison component
function PriceComparison({ offers, affiliateLinks }) {
  const supplierOffers = offers.filter(o => o.offerType === 'supplier');
  const affiliateOffers = offers.filter(o => o.offerType === 'affiliate');
  
  return (
    <div>
      <h3>Buy Direct</h3>
      {supplierOffers.map(offer => (
        <OfferCard key={offer.id} offer={offer} />
      ))}
      
      <h3>Also Available On</h3>
      {affiliateLinks.map(link => (
        <AffiliateLink key={link.platform} link={link} />
      ))}
    </div>
  );
}
```

### 4. Shopping Cart

```javascript
const CART_OPERATIONS = {
  getCart: `
    query GetCart($sessionId: String) {
      cart(sessionId: $sessionId) {
        id
        items {
          id
          quantity
          offer {
            product { name mainImage }
            sellingPrice
            vendor { name }
          }
        }
        totalAmount
      }
    }
  `,
  
  addToCart: `
    mutation AddToCart($sessionId: String, $item: CartItemInput!) {
      addToCart(sessionId: $sessionId, item: $item) {
        id
        totalAmount
      }
    }
  `
};
```

## Best Practices

### 1. Search Implementation
- Always use `unifiedProductSearch` for product discovery
- Display exact matches prominently
- Show alternatives as "Similar Products"
- Highlight affiliate opportunities with clear CTAs

### 2. Price Display
- Show supplier offers as "Buy Direct" with better margins
- Display affiliate links as "Also Available On Amazon" etc.
- Use `marginOpportunity` to prioritize display order

### 3. Performance
- Use pagination for large result sets
- Cache featured products
- Implement search-as-you-type with debouncing

### 4. Revenue Optimization
- Prioritize high-margin products
- Promote affiliate links for products without direct inventory
- Use cross-sell suggestions from `relationshipType: "accessory"`

## Error Handling

The API returns structured errors:

```graphql
{
  "errors": [
    {
      "message": "Product not found",
      "locations": [{"line": 2, "column": 3}],
      "path": ["product"]
    }
  ],
  "data": {
    "product": null
  }
}
```

## Rate Limiting

- No rate limiting on public queries
- Search queries are optimized for performance
- Amazon affiliate link generation may have delays (use `amazon_search_pending` status)

## Example Website Structure

```
Homepage
├── Featured Products (featuredProducts)
├── Categories (categories)
└── Search Bar (unifiedProductSearch)

Search Results
├── Exact Matches
├── Similar Products  
└── Compatible Accessories

Product Detail
├── Product Info
├── Price Comparison
├── Add to Cart
└── Related Products

Shopping Cart
├── Cart Items
├── Price Summary
└── Checkout
```

This API is designed to maximize revenue through intelligent product matching, competitive pricing, and affiliate link integration while providing a seamless shopping experience. 