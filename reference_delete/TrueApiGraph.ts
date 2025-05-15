import { ApolloClient, InMemoryCache, createHttpLink, gql, ApolloLink } from '@apollo/client/core';
import { setContext } from '@apollo/client/link/context';
import { onError } from "@apollo/client/link/error";
import { Observable } from "@apollo/client/utilities";
import jwt_decode from 'jwt-decode';
import { Operation } from '@apollo/client/core';

// Update the ApolloError interface with all needed properties
interface ApolloError {
  message: string;
  name: string;
  stack?: string;
  graphQLErrors?: any[];
  networkError?: {
    result?: any;
    bodyText?: string;
    [key: string]: any;
  };
  extraInfo?: any;
}

// Add this function to get the token
const getValidToken = async (): Promise<string> => {
  // Get the token from chrome storage
  const data = await chrome.storage.local.get('token');
  if (data.token) {
    return data.token;
  }
  throw new Error('No valid token found');
};

// Create Apollo Client instance
const httpLink = createHttpLink({
  // Use environment-based URL for production vs. development
  uri: process.env.NODE_ENV === 'production' 
    ? 'http://127.0.0.1:8000/graphql/' 
    : 'http://127.0.0.1:8000/graphql/',
});

const authLink = setContext(async (_, { headers }) => {
  // Get token from local storage
  let token;
  try {
    token = await getValidToken();
  } catch (error) {
    console.error('Error getting token', error);
  }
  
  return {
    headers: {
      ...headers,
      authorization: token ? `JWT ${token}` : "",
    }
  };
});

// Create an error link that handles token refresh
const errorLink = onError(({ graphQLErrors, networkError, operation, forward }) => {
  if (graphQLErrors) {
    for (const err of graphQLErrors) {
      // Check if error is due to authentication
      if (err.extensions?.code === 'UNAUTHENTICATED') {
        return new Observable(observer => {
          // Attempt to refresh token
          (async () => {
            try {
              // Get refresh token from storage
              const { refresh } = await chrome.storage.local.get('refresh');
              
              if (!refresh) {
                // No refresh token, can't recover
                observer.error(err);
                return;
              }
              
              // Try to get new tokens
              const refreshResult = await TrueGraphQLApi.refreshToken(refresh);
              
              if (!refreshResult.access) {
                // Refresh failed, can't recover
                observer.error(err);
                return;
              }
              
              // Retry the operation with new token
              const oldHeaders = operation.getContext().headers;
              operation.setContext({
                headers: {
                  ...oldHeaders,
                  authorization: `JWT ${refreshResult.access}`
                }
              });
              
              // Retry the request
              forward(operation).subscribe({
                next: observer.next.bind(observer),
                error: observer.error.bind(observer),
                complete: observer.complete.bind(observer)
              });
            } catch (refreshError) {
              // If refresh fails, clear tokens and redirect to login
              observer.error(refreshError);
              chrome.storage.local.remove(['token', 'refresh']);
            }
          })();
        });
      }
    }
  }
  
  if (networkError) {
    console.error(`[Network error]: ${networkError}`);
  }
});

// Update the GraphQLOperation interface
interface GraphQLOperation {
  query: any;
  variables: any;
  operationName: string;
  extensions: Record<string, any>;
  setContext: (context: Record<string, any>) => Record<string, any>;
  getContext: () => Record<string, any>;
}

// Create a detailed logging function with type annotations
const logFullResponse = (operation: GraphQLOperation, response: any) => {
  console.group(`🔍 GraphQL Raw Response - ${operation.operationName}`);
  console.log('Operation:', {
    query: operation.query.loc?.source.body,
    variables: operation.variables,
    operationName: operation.operationName
  });
  console.log('Raw Response Headers:', response.headers);
  console.log('Raw Response Status:', response.status);
  console.log('Raw Response Body:', response.body);
  console.groupEnd();
};

// Create a logging link with type annotations
const loggingLink = new ApolloLink((operation: Operation, forward) => {
  return forward(operation).map(response => {
    // Log the raw response
    console.group(`📡 GraphQL Raw Data - ${operation.operationName}`);
    console.log('Raw data:', response);
    console.log('Request variables:', operation.variables);
    if (response.errors) {
      console.error('GraphQL Errors:', response.errors);
    }
    console.groupEnd();
    return response;
  });
});

// Update client creation with error link
const client = new ApolloClient({
  link: errorLink.concat(authLink.concat(httpLink)),
  cache: new InMemoryCache()
});

// Add this logging utility at the top of your file
const logAuthInfo = (stage: string, data: any) => {
  console.group(`🔐 Auth Flow - ${stage}`);
  console.log(data);
  console.groupEnd();
};

// GraphQL API methods
const TrueGraphQLApi = {
  // Check if part exists
  check_part_exists: async (partNumber: string, asin?: string, url?: string): Promise<any> => {
    const { data } = await client.query({
      query: gql`
        query ProductExists($partNumber: String!, $asin: String, $url: String) {
          productExists(partNumber: $partNumber, asin: $asin, url: $url) {
            exists
            message
            product {
              id
              name
              partNumber
              mainImage
              affiliateLinks {
                id
                platform
                affiliateUrl
              }
              offers {
                id
                sellingPrice
                vendor {
                  name
                }
              }
            }
          }
        }
      `,
      variables: { partNumber, asin, url }
    });
    
    return data.productExists;
  },
  
  // Create Amazon affiliate link
  create_amazon_affiliate_link: async (asin: string): Promise<any> => {
    const { data } = await client.mutate({
      mutation: gql`
        mutation CreateAmazonAffiliateLink($asin: String!) {
          createAmazonAffiliateLink(asin: $asin) {
            affiliateLink {
              id
              platform
              platformId
              originalUrl
              affiliateUrl
            }
          }
        }
      `,
      variables: { asin }
    });
    
    return data.createAmazonAffiliateLink.affiliateLink;
  },
  
  // Create product with affiliate link
  create_part_with_affiliate: async (partData: any): Promise<any> => {
    const { data } = await client.mutate({
      mutation: gql`
        mutation CreateProductFromAmazon($input: AmazonProductInput!) {
          createProductFromAmazon(input: $input) {
            product {
              id
              name
              partNumber
              mainImage
              affiliateLinks {
                id
                affiliateUrl
              }
            }
          }
        }
      `,
      variables: { 
        input: {
          name: partData.name,
          description: partData.description,
          partNumber: partData.partNumber,
          manufacturerName: partData.manufacturer,
          asin: partData.asin,
          url: partData.url,
          image: partData.image,
          categoryName: partData.category
        } 
      }
    });
    
    return data.createProductFromAmazon.product;
  },
  
  // Cart operations
  add_to_cart: async (offerId: string, quantity: number): Promise<any> => {
    const { data } = await client.mutate({
      mutation: gql`
        mutation AddToCart($item: CartItemInput!) {
          addToCart(item: $item) {
            cart {
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
        }
      `,
      variables: { 
        item: { offerId, quantity }
      }
    });
    
    return data.addToCart.cart;
  },
  
  // Get cart
  get_cart: async (): Promise<any> => {
    const { data } = await client.query({
      query: gql`
        query GetCart {
          cart {
            id
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
                  id
                  name
                  partNumber
                  mainImage
                }
                vendor {
                  name
                }
              }
            }
          }
        }
      `
    });
    
    return data.cart;
  },
  // Add a debug query to check authentication
debug_auth: async (): Promise<any> => {
  console.group('🔧 Auth Debugging');
  console.log('Running direct auth check');
  
  try {
    const result = await client.query({
      query: gql`
        query DebugAuth {
          currentUserDebug {
            id
            email
            firstName
            lastName
            wallet
          }
        }
      `,
      fetchPolicy: 'network-only',
      errorPolicy: 'all'
    });
    
    console.log('Debug query result:', result);
    
    if (result.errors) {
      console.error('Debug errors:', result.errors);
    } else {
      console.log('Debug user data:', result.data?.currentUserDebug);
    }
    
    console.groupEnd();
    return result.data?.currentUserDebug;
  } catch (error) {
    console.error('Debug query error:', error);
    console.groupEnd();
    throw error;
  }
},

  // Login functionality
 // Update your login method to match the expected mutation
login: async (email : string, password : string) => {
  try {
    const { data } = await client.mutate({
      mutation: gql`
        mutation TokenAuth($email: String!, $password: String!) {
          tokenAuth(email: $email, password: $password) {
            token
            refreshToken
            payload
          }
        }
      `,
      variables: { email, password }
    });
    
    // Store tokens
    await chrome.storage.local.set({
      token: data.tokenAuth.token,
      refresh: data.tokenAuth.refreshToken  
    });
    
    return {
      access: data.tokenAuth.token,
      refresh: data.tokenAuth.refreshToken,
      payload: data.tokenAuth.payload
    };
  } catch (error) {
    console.error('Login error:', error);
    throw error;
  }
},

// Me query
fetch_user_details: async () => {
  try {
    // Ensure authentication header is set correctly
    const result = await client.query({
      query: gql`
        query Me {
          me {
            id
            email
            firstName
            lastName
            wallet
          }
        }
      `,
      fetchPolicy: 'network-only'  // Don't use cache
    });
    
    return result.data.me;
  } catch (error) {
    console.error('Error fetching user details:', error);
    throw error;
  }
},
  // Product lookup by part number
  query_by_part_number: async (partNumber: string): Promise<any> => {
    const { data } = await client.query({
      query: gql`
        query ProductByPartNumber($partNumber: String!) {
          productByPartNumber(partNumber: $partNumber) {
            id
            name
            partNumber
            description
            mainImage
            manufacturer {
              id
              name
            }
            offers {
              id
              sellingPrice
              vendor {
                name
              }
            }
          }
        }
      `,
      variables: { partNumber }
    });
    
    return data.productByPartNumber;
  },

  // Product lookup by name
  query_by_name: async (name: string): Promise<any> => {
    const { data } = await client.query({
      query: gql`
        query ProductSearch($name: String!) {
          productsSearch(searchTerm: $name, first: 1) {
            edges {
              node {
                id
                name
                partNumber
                description
                mainImage
                manufacturer {
                  name
                }
                offers {
                  id
                  sellingPrice
                  vendor {
                    name
                  }
                }
              }
            }
          }
        }
      `,
      variables: { name }
    });
    
    return data.productsSearch.edges.length > 0 
      ? data.productsSearch.edges[0].node 
      : null;
  },

  // Get store products (paginated)
  get_store_products: async (params?: string): Promise<any> => {
    // Parse pagination parameters if provided
    const page = params?.includes('page=') 
      ? parseInt(params.match(/page=(\d+)/)?.[1] || '1') 
      : 1;
    const pageSize = 20;
    
    const { data } = await client.query({
      query: gql`
        query GetStoreProducts($page: Int, $pageSize: Int) {
          products(page: $page, pageSize: $pageSize) {
            totalCount
            hasNextPage
            hasPreviousPage
            edges {
              node {
                id
                name
                partNumber
                mainImage
                manufacturer {
                  name
                }
                offers {
                  id
                  sellingPrice
                  vendor {
                    name
                  }
                }
              }
            }
          }
        }
      `,
      variables: { page, pageSize }
    });
    
    // Convert to format expected by existing code
    return {
      count: data.products.totalCount,
      next: data.products.hasNextPage ? `page=${page + 1}` : null,
      previous: data.products.hasPreviousPage ? `page=${page - 1}` : null,
      results: data.products.edges.map((edge: any) => edge.node)
    };
  },

  // Search store products
  search_store_products: async (term: string, price?: number, link?: string): Promise<any> => {
    const { data } = await client.query({
      query: gql`
        query SearchProducts($term: String!, $price: Float) {
          productsSearch(partNumber: $term, maxPrice: $price) {
            edges {
              node {
                id
                name
                partNumber
                mainImage
                manufacturer {
                  name
                }
                offers {
                  id
                  sellingPrice
                  vendor {
                    name
                  }
                }
              }
            }
          }
        }
      `,
      variables: { term, price }
    });
    
    return data.productsSearch.edges.map((edge: any) => edge.node);
  },

  // Search by name
  search_store_products_by_name: async (term: string, price?: number, link?: string): Promise<any> => {
    const { data } = await client.query({
      query: gql`
        query SearchProductsByName($term: String!, $price: Float) {
          productsSearch(searchTerm: $term, maxPrice: $price) {
            edges {
              node {
                id
                name
                partNumber
                mainImage
                manufacturer {
                  name
                }
                offers {
                  id
                  sellingPrice
                  vendor {
                    name
                  }
                }
              }
            }
          }
        }
      `,
      variables: { term, price }
    });
    
    return data.productsSearch.edges.map((edge: any) => edge.node);
  },

  // Get detailed product info
  get_item_details: async (itemId: string): Promise<any> => {
    const { data } = await client.query({
      query: gql`
        query GetProductDetails($id: ID!) {
          product(id: $id) {
            id
            name
            partNumber
            description
            mainImage
            manufacturer {
              id
              name
            }
            categories {
              id
              name
            }
            offers {
              id
              sellingPrice
              stockQuantity
              isInStock
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
      `,
      variables: { id: itemId }
    });
    
    return data.product;
  },

  // Add token refresh functionality
  refreshToken: async (refreshToken: string): Promise<any> => {
    logAuthInfo('Refreshing Token', { refreshTokenLength: refreshToken?.length });
    
    try {
      const { data } = await client.mutate({
        mutation: gql`
          mutation RefreshToken($refreshToken: String!) {
            refreshToken(refreshToken: $refreshToken) {
              token
              refreshToken
              payload
            }
          }
        `,
        variables: { refreshToken }
      });
      
      logAuthInfo('Token Refresh Response', data);
      
      // Store new tokens
      await chrome.storage.local.set({
        token: data.refreshToken.token,
        refresh: data.refreshToken.refreshToken
      });
      
      return {
        access: data.refreshToken.token,
        refresh: data.refreshToken.refreshToken,
        payload: data.refreshToken.payload
      };
    } catch (error) {
      logAuthInfo('Token Refresh Error', {
        error,
        message: (error as ApolloError).message,
        graphQLErrors: (error as ApolloError).graphQLErrors,
        networkError: (error as ApolloError).networkError
      });
      throw error;
    }
  },

  // Update your token verification with enhanced logging
  verifyToken: async (token: string): Promise<boolean> => {
    console.group('🔐 Token Verification');
    console.log('Token to verify:', token ? `${token.substring(0, 15)}...` : 'No token');
    
    try {
      // Log the raw request
      console.log('Sending verification request');
      
      const { data, errors } = await client.mutate({
        mutation: gql`
          mutation VerifyToken($token: String!) {
            verifyToken(token: $token) {
              payload
            }
          }
        `,
        variables: { token }
      });
      
      // Log the full response
      console.log('Verification response data:', data);
      if (errors) {
        console.error('Verification response errors:', errors);
      }
      
      console.groupEnd();
      return !!data.verifyToken?.payload;
    } catch (error) {
      console.error('Token Verification Error:', {
        error,
        message: (error as ApolloError).message,
        name: (error as ApolloError).name,
        stack: (error as ApolloError).stack,
        graphQLErrors: (error as ApolloError).graphQLErrors?.map(e => ({
          message: e.message,
          locations: e.locations,
          path: e.path,
          extensions: e.extensions
        })),
        networkError: (error as ApolloError).networkError,
        extraInfo: (error as ApolloError).extraInfo
      });
      console.groupEnd();
      return false;
    }
  },

  register: async (email: string, password: string, firstName: string, lastName: string): Promise<any> => {
    const { data } = await client.mutate({
      mutation: gql`
        mutation RegisterUser(
          $email: String!, 
          $password: String!, 
          $firstName: String!, 
          $lastName: String!
        ) {
          register(
            email: $email,
            password: $password,
            firstName: $firstName,
            lastName: $lastName
          ) {
            success
            errors
            user {
              id
              email
            }
          }
        }
      `,
      variables: { email, password, firstName, lastName }
    });
    
    if (!data.register.success) {
      throw new Error(data.register.errors);
    }
    
    return data.register.user;
  },

  // Add this method to your TrueGraphQLApi object
  removeFromCart: async (cartItemId: number | string): Promise<boolean> => {
    const { data } = await client.mutate({
      mutation: gql`
        mutation RemoveFromCart($cartItemId: ID!) {
          removeFromCart(input: { cartItemId: $cartItemId }) {
            success
          }
        }
      `,
      variables: { cartItemId: String(cartItemId) }
    });
    
    return data.removeFromCart.success;
  },

  // Add this to TrueGraphQLApi object
  update_cart_item_quantity: async (cartItemId: number | string, quantity: number): Promise<any> => {
    const { data } = await client.mutate({
      mutation: gql`
        mutation UpdateCartItemQuantity($cartItemId: ID!, $quantity: Int!) {
          updateCartItemQuantity(input: { cartItemId: $cartItemId, quantity: $quantity }) {
            cartItem {
              id
              quantity
              totalPrice
              offer {
                id
                sellingPrice
                product {
                  id
                  name
                  partNumber
                  mainImage
                }
                vendor {
                  name
                }
              }
            }
          }
        }
      `,
      variables: { cartItemId: String(cartItemId), quantity }
    });
    
    return data.updateCartItemQuantity.cartItem;
  },

  // Add these methods to your TrueGraphQLApi object
  getProducts: async (offset = 0, limit = 20): Promise<any> => {
    try {
      const { data } = await client.query({
        query: gql`
          query Products($limit: Int, $offset: Int) {
            products(limit: $limit, offset: $offset) {
              totalCount
              items {
                id
                name
                description
                mainImage
                partNumber
                manufacturer {
                  id
                  name
                }
                categories {
                  id
                  name
                }
              }
            }
          }
        `,
        variables: {
          offset,
          limit
        },
        fetchPolicy: 'network-only'
      });
      
      return data.products;
    } catch (error) {
      console.error('Error in getProducts:', error);
      throw error;
    }
  },

  searchProducts: async (term: string, offset = 0, limit = 20): Promise<any> => {
    try {
      const { data } = await client.query({
        query: gql`
          query Products($search: String, $limit: Int, $offset: Int) {
            products(search: $search, limit: $limit, offset: $offset) {
              totalCount
              items {
                id
                name
                description
                mainImage
                partNumber
                manufacturer {
                  id
                  name
                }
                categories {
                  id
                  name
                }
              }
            }
          }
        `,
        variables: {
          search: term,
          offset,
          limit
        },
        fetchPolicy: 'network-only'
      });
      
      return data.products;
    } catch (error) {
      console.error('Error in searchProducts:', error);
      throw error;
    }
  },

  getProductById: async (id: string): Promise<any> => {
    try {
      const { data } = await client.query({
        query: gql`
          query Product($id: ID) {
            product(id: $id) {
              id
              name
              description
              mainImage
              additionalImages
              partNumber
              specifications
              dimensions {
                length
                width
                height
              }
              manufacturer {
                id
                name
              }
              categories {
                id
                name
              }
            }
          }
        `
      });
      
      return data.product;
    } catch (error) {
      console.error('Error in getProductById:', error);
      throw error;
    }
  }
};

// Add this export statement at the end of the file
export default TrueGraphQLApi;