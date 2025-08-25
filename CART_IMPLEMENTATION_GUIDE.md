# Cart Implementation Guide

## Table of Contents
1. [Overview](#overview)
2. [Backend Architecture](#backend-architecture)
3. [GraphQL API Reference](#graphql-api-reference)
4. [Frontend Implementation](#frontend-implementation)
5. [Session Management](#session-management)
6. [Authentication Integration](#authentication-integration)
7. [Error Handling](#error-handling)
8. [Testing Strategy](#testing-strategy)
9. [Performance Considerations](#performance-considerations)
10. [Known Issues & Improvements](#known-issues--improvements)

## Overview

This document provides comprehensive guidance for implementing shopping cart functionality in frontend clients (website and Chrome extension). The cart system supports both authenticated and anonymous users with seamless session management.

### Key Features
- ✅ Anonymous cart support via session IDs
- ✅ Authenticated user carts
- ✅ Cart persistence across sessions
- ✅ Real-time cart totals calculation
- ✅ Duplicate item handling (quantity aggregation)
- ✅ Offer-based cart items
- ✅ Django admin interface with convenience methods
- ✅ Model convenience methods for totals and item counts
- ❌ Cart merging on login (needs implementation)
- ❌ Cart expiration (needs implementation)
- ❌ Save for later functionality (needs implementation)

## Backend Architecture

### Database Schema

```sql
-- Cart table
CREATE TABLE store_cart (
    id BIGINT PRIMARY KEY,
    user_id INT NULL,                    -- FK to auth_user
    session_id VARCHAR(100),             -- For anonymous users
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    CONSTRAINT cart_user_or_session CHECK (user_id IS NOT NULL OR session_id != '')
);

-- Cart items table
CREATE TABLE store_cartitem (
    id BIGINT PRIMARY KEY,
    cart_id BIGINT,                      -- FK to store_cart
    offer_id BIGINT,                     -- FK to offers_offer
    quantity INT DEFAULT 1,
    added_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(cart_id, offer_id)            -- One offer per cart
);
```

### Models Overview

**Cart Model:**
- Supports both authenticated users (`user` field) and anonymous sessions (`session_id`)
- Database constraint ensures either `user` OR `session_id` is present
- Automatically tracks creation and update timestamps
- **Convenience methods:**
  - `item_count` (property): Returns total number of items in cart
  - `total_price` (property): Returns total price of all items
  - `get_user_display()` (method): Returns user-friendly display string

**CartItem Model:**
- Links to specific `Offer` objects (not products directly)
- Enforces uniqueness per cart+offer combination
- Quantity aggregation when same offer is added multiple times
- **Convenience methods:**
  - `total_price` (property): Returns `quantity * offer.selling_price`
  - `unit_price` (property): Returns `offer.selling_price`

**Offer Model (Related):**
- Supports multiple offer types: `supplier`, `affiliate`, `quote`
- Contains pricing information (`selling_price`, `cost_price`, `msrp`)
- Links to `Product` and `Vendor` models
- Tracks availability and stock status

### Django Admin Interface

The Cart models now have a comprehensive Django admin interface:

**CartAdmin Features:**
- User-friendly display with formatted prices
- Search by username, email, or session ID
- Collapsible sections for statistics and timestamps
- Optimized queries with `select_related` and `prefetch_related`
- Read-only calculated fields (item_count, total_price)

**CartItemAdmin Features:**
- Product information display with part numbers
- Formatted pricing display
- Cart relationship information
- Search across multiple related fields

## GraphQL API Reference

### Queries

#### Get Cart
```graphql
query GetCart($sessionId: String, $id: ID) {
  cart(sessionId: $sessionId, id: $id) {
    id
    sessionId
    user {
      id
      email
    }
    items {
      id
      quantity
      addedAt
      offer {
        id
        sellingPrice
        vendor {
          name
        }
        product {
          id
          name
          partNumber
          mainImage
        }
      }
      totalPrice  # quantity * offer.sellingPrice
    }
    totalItems    # sum of all quantities
    totalPrice    # sum of all item totals
    createdAt
    updatedAt
  }
}
```

**Parameters:**
- `sessionId` (String, optional): Session ID for anonymous users
- `id` (ID, optional): Direct cart ID lookup

**Resolution Logic:**
1. If `id` provided → return specific cart
2. If `sessionId` provided → find cart by session ID
3. If user authenticated → find user's cart
4. Otherwise → return null

### Mutations

#### Add to Cart
```graphql
mutation AddToCart($sessionId: String, $cartId: ID, $item: CartItemInput!) {
  addToCart(sessionId: $sessionId, cartId: $cartId, item: $item) {
    id
    totalItems
    totalPrice
    items {
      id
      quantity
      offer {
        id
        sellingPrice
        product {
          name
          partNumber
        }
      }
    }
  }
}
```

**Input Type:**
```graphql
input CartItemInput {
  offerId: ID!      # Required: Offer to add
  quantity: Int!    # Required: Quantity to add
}
```

**Behavior:**
- Creates new cart if none exists
- Generates UUID session ID for anonymous users
- Aggregates quantity if offer already in cart
- Returns full cart with updated totals

#### Update Cart Item
```graphql
mutation UpdateCartItem($id: ID!, $quantity: Int!) {
  updateCartItem(id: $id, quantity: $quantity) {
    id
    quantity
    totalPrice
  }
}
```

**Behavior:**
- Updates quantity of specific cart item
- Sets quantity to 0 deletes the item
- Returns updated cart item or null if deleted

#### Remove from Cart
```graphql
mutation RemoveFromCart($id: ID!) {
  removeFromCart(id: $id)  # Returns Boolean
}
```

#### Clear Cart
```graphql
mutation ClearCart($cartId: ID, $sessionId: String) {
  clearCart(cartId: $cartId, sessionId: $sessionId)  # Returns Boolean
}
```

**Parameters:**
- Either `cartId` OR `sessionId` required
- Removes all items from the specified cart

## Frontend Implementation

### 1. Session Management

```typescript
// Generate consistent session ID
function generateSessionId(): string {
  return `cart_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

// Store session ID
function getOrCreateSessionId(): string {
  let sessionId = localStorage.getItem('cart_session_id');
  if (!sessionId) {
    sessionId = generateSessionId();
    localStorage.setItem('cart_session_id', sessionId);
  }
  return sessionId;
}
```

### 2. Cart State Management

```typescript
interface CartItem {
  id: string;
  quantity: number;
  addedAt: string;
  offer: {
    id: string;
    sellingPrice: number;
    vendor: {
      name: string;
    };
    product: {
      id: string;
      name: string;
      partNumber: string;
      mainImage?: string;
    };
  };
  totalPrice: number;
}

interface Cart {
  id: string;
  sessionId?: string;
  items: CartItem[];
  totalItems: number;
  totalPrice: number;
  createdAt: string;
  updatedAt: string;
}

class CartManager {
  private cart: Cart | null = null;
  private sessionId: string;

  constructor() {
    this.sessionId = getOrCreateSessionId();
  }

  async loadCart(): Promise<Cart | null> {
    const { data } = await client.query({
      query: GET_CART_QUERY,
      variables: { sessionId: this.sessionId },
      fetchPolicy: 'network-only'  // Always get fresh data
    });
    
    this.cart = data.cart;
    return this.cart;
  }

  async addItem(offerId: string, quantity: number = 1): Promise<Cart> {
    const { data } = await client.mutate({
      mutation: ADD_TO_CART_MUTATION,
      variables: {
        sessionId: this.sessionId,
        item: { offerId, quantity }
      }
    });
    
    this.cart = data.addToCart;
    this.saveToLocalStorage();
    return this.cart;
  }

  async updateItem(itemId: string, quantity: number): Promise<void> {
    await client.mutate({
      mutation: UPDATE_CART_ITEM_MUTATION,
      variables: { id: itemId, quantity }
    });
    
    // Reload cart to get updated totals
    await this.loadCart();
  }

  async removeItem(itemId: string): Promise<void> {
    await client.mutate({
      mutation: REMOVE_FROM_CART_MUTATION,
      variables: { id: itemId }
    });
    
    await this.loadCart();
  }

  async clearCart(): Promise<void> {
    if (!this.cart) return;
    
    await client.mutate({
      mutation: CLEAR_CART_MUTATION,
      variables: { sessionId: this.sessionId }
    });
    
    this.cart = null;
    this.clearLocalStorage();
  }

  // Local storage for offline access
  private saveToLocalStorage(): void {
    if (this.cart) {
      localStorage.setItem('cart_data', JSON.stringify(this.cart));
    }
  }

  private clearLocalStorage(): void {
    localStorage.removeItem('cart_data');
  }

  getItemCount(): number {
    return this.cart?.totalItems || 0;
  }

  getTotalPrice(): number {
    return this.cart?.totalPrice || 0;
  }
}
```

### 3. GraphQL Queries & Mutations

```typescript
const GET_CART_QUERY = gql`
  query GetCart($sessionId: String) {
    cart(sessionId: $sessionId) {
      id
      sessionId
      items {
        id
        quantity
        addedAt
        offer {
          id
          sellingPrice
          vendor {
            name
          }
          product {
            id
            name
            partNumber
            mainImage
          }
        }
        totalPrice
      }
      totalItems
      totalPrice
      createdAt
      updatedAt
    }
  }
`;

const ADD_TO_CART_MUTATION = gql`
  mutation AddToCart($sessionId: String, $item: CartItemInput!) {
    addToCart(sessionId: $sessionId, item: $item) {
      id
      totalItems
      totalPrice
      items {
        id
        quantity
        offer {
          id
          sellingPrice
          product {
            name
            partNumber
            mainImage
          }
        }
        totalPrice
      }
    }
  }
`;

const UPDATE_CART_ITEM_MUTATION = gql`
  mutation UpdateCartItem($id: ID!, $quantity: Int!) {
    updateCartItem(id: $id, quantity: $quantity) {
      id
      quantity
      totalPrice
    }
  }
`;

const REMOVE_FROM_CART_MUTATION = gql`
  mutation RemoveFromCart($id: ID!) {
    removeFromCart(id: $id)
  }
`;

const CLEAR_CART_MUTATION = gql`
  mutation ClearCart($sessionId: String) {
    clearCart(sessionId: $sessionId)
  }
`;
```

### 4. React Components Example

```typescript
// Cart Icon Component
const CartIcon: React.FC = () => {
  const [itemCount, setItemCount] = useState(0);
  const cartManager = new CartManager();

  useEffect(() => {
    const loadCartCount = async () => {
      const cart = await cartManager.loadCart();
      setItemCount(cart?.totalItems || 0);
    };
    
    loadCartCount();
  }, []);

  return (
    <div className="cart-icon">
      🛒
      {itemCount > 0 && (
        <span className="cart-badge">{itemCount}</span>
      )}
    </div>
  );
};

// Add to Cart Button
const AddToCartButton: React.FC<{ offerId: string }> = ({ offerId }) => {
  const [loading, setLoading] = useState(false);
  const cartManager = new CartManager();

  const handleAddToCart = async () => {
    setLoading(true);
    try {
      await cartManager.addItem(offerId, 1);
      // Show success notification
    } catch (error) {
      // Show error notification
      console.error('Failed to add to cart:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button 
      onClick={handleAddToCart} 
      disabled={loading}
      className="add-to-cart-btn"
    >
      {loading ? 'Adding...' : 'Add to Cart'}
    </button>
  );
};
```

### 5. Chrome Extension Implementation

```typescript
// Background script
class ExtensionCartManager extends CartManager {
  constructor() {
    super();
    this.setupMessageListener();
  }

  private setupMessageListener(): void {
    chrome.runtime.onMessage.addListener(
      (request, sender, sendResponse) => {
        this.handleMessage(request, sender, sendResponse);
      }
    );
  }

  private async handleMessage(request: any, sender: any, sendResponse: any): Promise<void> {
    switch (request.action) {
      case 'ADD_TO_CART':
        try {
          const cart = await this.addItem(request.offerId, request.quantity);
          sendResponse({ success: true, cart });
        } catch (error) {
          sendResponse({ success: false, error: error.message });
        }
        break;

      case 'GET_CART':
        try {
          const cart = await this.loadCart();
          sendResponse({ success: true, cart });
        } catch (error) {
          sendResponse({ success: false, error: error.message });
        }
        break;
    }
  }
}

// Content script
function addToCartFromPage(offerId: string): void {
  chrome.runtime.sendMessage({
    action: 'ADD_TO_CART',
    offerId,
    quantity: 1
  }, (response) => {
    if (response.success) {
      showNotification('Added to cart!');
    } else {
      showNotification('Failed to add to cart: ' + response.error);
    }
  });
}
```

## Authentication Integration

### Anonymous to Authenticated User Migration

**Current Limitation:** Cart merging on login is not implemented. This needs to be added.

**Recommended Implementation:**

```typescript
class AuthCartManager extends CartManager {
  async handleUserLogin(authToken: string): Promise<void> {
    // Get current anonymous cart
    const anonymousCart = await this.loadCart();
    
    // Update client to use auth token
    this.updateAuthToken(authToken);
    
    // Get or create authenticated user cart
    const userCart = await this.loadCart();
    
    // Merge carts if anonymous cart exists
    if (anonymousCart && anonymousCart.items.length > 0) {
      await this.mergeAnonymousCart(anonymousCart, userCart);
    }
  }

  private async mergeAnonymousCart(anonymousCart: Cart, userCart: Cart | null): Promise<void> {
    // This functionality needs to be implemented in the backend
    // For now, we'll add items individually
    for (const item of anonymousCart.items) {
      await this.addItem(item.offer.id, item.quantity);
    }
    
    // Clear anonymous cart
    await client.mutate({
      mutation: CLEAR_CART_MUTATION,
      variables: { sessionId: anonymousCart.sessionId }
    });
  }
}
```

## Error Handling

### Common Error Scenarios

1. **Offer Not Found**
   ```typescript
   try {
     await cartManager.addItem(offerId, quantity);
   } catch (error) {
     if (error.message.includes('Offer with ID')) {
       showError('This item is no longer available');
     }
   }
   ```

2. **Network Errors**
   ```typescript
   try {
     await cartManager.loadCart();
   } catch (error) {
     // Fall back to local storage
     const cachedCart = localStorage.getItem('cart_data');
     if (cachedCart) {
       this.cart = JSON.parse(cachedCart);
     }
   }
   ```

3. **Invalid Quantities**
   ```typescript
   const updateQuantity = async (itemId: string, quantity: number) => {
     if (quantity < 0) {
       throw new Error('Quantity cannot be negative');
     }
     
     if (quantity === 0) {
       return await cartManager.removeItem(itemId);
     }
     
     return await cartManager.updateItem(itemId, quantity);
   };
   ```

## Testing Strategy

### Unit Tests

```typescript
describe('CartManager', () => {
  let cartManager: CartManager;
  
  beforeEach(() => {
    cartManager = new CartManager();
    // Mock localStorage
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: jest.fn(),
        setItem: jest.fn(),
        removeItem: jest.fn(),
        clear: jest.fn(),
      },
      writable: true,
    });
  });

  test('should generate session ID if none exists', () => {
    (localStorage.getItem as jest.Mock).mockReturnValue(null);
    const sessionId = getOrCreateSessionId();
    expect(sessionId).toMatch(/^cart_\d+_\w+$/);
    expect(localStorage.setItem).toHaveBeenCalledWith('cart_session_id', sessionId);
  });

  test('should add item to cart', async () => {
    const mockCart = {
      id: '1',
      items: [],
      totalItems: 1,
      totalPrice: 99.99
    };
    
    const mockMutate = jest.fn().mockResolvedValue({
      data: { addToCart: mockCart }
    });
    
    await cartManager.addItem('offer-1', 1);
    expect(mockMutate).toHaveBeenCalledWith({
      mutation: ADD_TO_CART_MUTATION,
      variables: {
        sessionId: expect.any(String),
        item: { offerId: 'offer-1', quantity: 1 }
      }
    });
  });
});
```

### Integration Tests

```typescript
describe('Cart Integration', () => {
  test('should persist cart across browser sessions', async () => {
    // Add item to cart
    const cartManager1 = new CartManager();
    await cartManager1.addItem('offer-1', 2);
    
    // Simulate new browser session
    const cartManager2 = new CartManager();
    const cart = await cartManager2.loadCart();
    
    expect(cart?.items).toHaveLength(1);
    expect(cart?.items[0].quantity).toBe(2);
  });
  
  test('should handle cart merging on login', async () => {
    // Add items as anonymous user
    const cartManager = new CartManager();
    await cartManager.addItem('offer-1', 1);
    await cartManager.addItem('offer-2', 2);
    
    // Login user
    await cartManager.handleUserLogin('auth-token');
    
    // Verify items are preserved
    const cart = await cartManager.loadCart();
    expect(cart?.items).toHaveLength(2);
  });
});
```

## Performance Considerations

### 1. Caching Strategy
- Cache cart data in localStorage for offline access
- Use GraphQL cache for frequently accessed cart data
- Implement optimistic updates for better UX

### 2. Query Optimization
```typescript
// Use fragments for consistent field selection
const CART_FRAGMENT = gql`
  fragment CartFields on Cart {
    id
    sessionId
    totalItems
    totalPrice
    items {
      id
      quantity
      totalPrice
      offer {
        id
        sellingPrice
        product {
          name
          partNumber
          mainImage
        }
      }
    }
  }
`;

const GET_CART_QUERY = gql`
  query GetCart($sessionId: String) {
    cart(sessionId: $sessionId) {
      ...CartFields
    }
  }
  ${CART_FRAGMENT}
`;
```

### 3. Debounced Updates
```typescript
const debouncedUpdateQuantity = debounce(async (itemId: string, quantity: number) => {
  await cartManager.updateItem(itemId, quantity);
}, 500);
```

## Known Issues & Improvements

### Recently Implemented ✅

1. **✅ Django Admin Interface**
   - **Status**: Completed
   - **Features**: Full admin interface with formatted displays, search functionality, and optimized queries

2. **✅ Model Convenience Methods**
   - **Status**: Completed
   - **Features**: 
     - `Cart.item_count` property
     - `Cart.total_price` property
     - `Cart.get_user_display()` method
     - `CartItem.total_price` property
     - `CartItem.unit_price` property

### Critical Issues Still Needed

1. **❌ Cart Merging on Login**
   - **Issue**: Anonymous carts are not merged when users log in
   - **Impact**: Users lose cart contents when logging in
   - **Solution**: Implement backend mutation for cart merging

2. **❌ Cart Expiration**
   - **Issue**: No automatic cart cleanup
   - **Impact**: Database bloat from abandoned carts
   - **Solution**: Add TTL field and background cleanup task

3. **❌ Stock Validation**
   - **Issue**: No stock checking when adding items
   - **Impact**: Users can add out-of-stock items
   - **Solution**: Validate offer availability in mutations

### Enhancements Needed

1. **Save for Later**
   ```sql
   -- Add wishlist/saved items table
   CREATE TABLE store_saveditem (
       id BIGINT PRIMARY KEY,
       cart_id BIGINT,
       offer_id BIGINT,
       saved_at TIMESTAMP
   );
   ```

2. **Cart Abandonment Recovery**
   - Email notifications for abandoned carts
   - Analytics tracking for cart abandonment

3. **Price Change Notifications**
   - Alert users if item prices change in cart
   - Update cart totals automatically

4. **Bulk Operations**
   ```graphql
   mutation BulkUpdateCart($updates: [CartItemUpdateInput!]!) {
     bulkUpdateCart(updates: $updates) {
       success
       cart { ...CartFields }
     }
   }
   ```

### Recommended Backend Improvements

```python
# store/models.py - Add to Cart model
class Cart(models.Model):
    # ... existing fields ...
    expires_at = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    def extend_expiration(self):
        """Extend cart expiration by 30 days"""
        from django.utils import timezone
        from datetime import timedelta
        self.expires_at = timezone.now() + timedelta(days=30)
        self.save()

# New mutation for cart merging
class MergeAnonymousCart(graphene.Mutation):
    class Arguments:
        anonymous_session_id = graphene.String(required=True)
    
    cart = graphene.Field(CartType)
    
    @staticmethod
    def mutate(root, info, anonymous_session_id):
        user = info.context.user
        if not user.is_authenticated:
            raise GraphQLError("Authentication required")
        
        # Get anonymous cart
        anonymous_cart = Cart.objects.filter(
            session_id=anonymous_session_id
        ).first()
        
        if not anonymous_cart:
            return MergeAnonymousCart(cart=None)
        
        # Get or create user cart
        user_cart, created = Cart.objects.get_or_create(
            user=user,
            defaults={'session_id': ''}
        )
        
        # Merge items
        for anon_item in anonymous_cart.items.all():
            user_item, created = CartItem.objects.get_or_create(
                cart=user_cart,
                offer=anon_item.offer,
                defaults={'quantity': anon_item.quantity}
            )
            if not created:
                user_item.quantity += anon_item.quantity
                user_item.save()
        
        # Delete anonymous cart
        anonymous_cart.delete()
        
        return MergeAnonymousCart(cart=user_cart)

# Add stock validation to AddToCart mutation
class AddToCart(graphene.Mutation):
    # ... existing code ...
    
    @staticmethod
    def mutate(root, info, item, session_id=None, cart_id=None):
        try:
            # ... existing cart creation logic ...
            
            # Get the offer and validate stock
            offer = Offer.objects.get(pk=item.offer_id)
            
            if not offer.is_active or not offer.is_in_stock:
                raise GraphQLError(f"Offer {item.offer_id} is not available")
            
            if offer.stock_quantity > 0 and item.quantity > offer.stock_quantity:
                raise GraphQLError(f"Only {offer.stock_quantity} items available")
            
            # ... rest of existing logic ...
```

### Security Considerations

1. **Session ID Validation**
   - Validate session ID format
   - Rate limit cart operations

2. **Authentication Context**
   - Ensure proper user context in mutations
   - Prevent cart access across users

3. **Input Validation**
   - Validate quantity limits
   - Sanitize offer IDs

## Conclusion

The cart implementation now provides a robust foundation for e-commerce functionality with:

### ✅ Recently Completed
- **Django Admin Interface**: Full-featured admin with optimized queries and user-friendly displays
- **Model Convenience Methods**: Properties and methods for calculating totals and item counts
- **Comprehensive Documentation**: Complete implementation guide for frontend teams

### 📋 Next Priority Tasks
1. **Cart Merging**: Implement seamless login experience 
2. **Stock Validation**: Prevent out-of-stock items from being added
3. **Cart Expiration**: Add TTL and cleanup mechanisms
4. **Test Coverage**: Comprehensive unit and integration tests

The current implementation provides frontend teams with all the tools needed to build robust cart functionality. The GraphQL API is complete, the backend models are optimized with convenience methods, and the admin interface allows for proper oversight.

**Frontend teams can now:**
- Implement cart functionality using the provided examples
- Handle both anonymous and authenticated users
- Display real-time cart totals and item counts
- Build comprehensive cart management UIs

**Admin teams can now:**
- Monitor cart activity through the Django admin
- View formatted pricing and user information
- Search and filter carts effectively
- Access calculated totals without manual computation

