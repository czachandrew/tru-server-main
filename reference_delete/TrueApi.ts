import { CartItem, DetailResponse } from '@/stores/types.d';

const baseUrl = 'http://127.0.0.1:8000/api/';
// const baseUrl = 'https://switchboard-backend.herokuapp.com/api/';

interface RequestBody {
  [index: string]: string | any;
}

interface TrueToken {
  access: string;
  refresh: string;
}

interface OfferItem {
  name: string;
  description: string;
  mfr_part: string;
  reseller_part: string;
  provider: string;
  url: string;
}

interface QueryPayload {
  name?: string;
  mfr_part?: string;
  manufacturer?: string;
}

const getFromLocalStorage = (key: string): Promise<string> =>
  new Promise((resolve, reject) => {
    chrome.storage.local.get([key], result => {
      if (result[key] === undefined) {
        reject();
      } else {
        resolve(result[key]);
      }
    });
  });

const getFreshToken = (refreshToken: string): Promise<string> =>
  new Promise((resolve, reject) => {
    fetch(`${baseUrl}token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: refreshToken }),
    })
      .then(async response => {
        console.log(response);
        const data = await response.json();
        console.log(data);
        chrome.storage.local.set({ token: data.access });
        resolve(data.access);
      })
      .catch(error => {
        console.log('there was and error refreshing');
        console.log(error);

        return reject(new Error('There was an error refreshing'));
      });
  });
/**
 * This method will check local for token, ensure that it isn't expired,
 * if it is we will refresh the token or promt user to re-login
 */
const getValidToken = async (): Promise<string | boolean> => {
  console.log("Let's get our token figured");
  const token = await getFromLocalStorage('token');
  const decodedToken = JSON.parse(atob(token.split('.')[1]));
  const refreshToken = await getFromLocalStorage('refresh');
  const decodedRefresh = JSON.parse(atob(refreshToken.split('.')[1]));
  // current date value
  const now = Math.ceil(Date.now() / 1000);

  if (token === undefined && refreshToken === undefined) {
    return false;
  }
  if (decodedToken.exp > now) {
    console.log('the original token is not expired');
    return token;
  }
  if (decodedRefresh.exp > now) {
    // post a request to '/token/refresh/
    console.log('using the refresh tokne now');
    const newtoken = await getFreshToken(refreshToken);
    return newtoken;
    // ok here we go
  }
  console.log('uh oh the refresh tokne is also expired');
  return false;
};

const executeRequest = async (
  endpoint: string,
  method: string,
  body?: RequestBody,
  requireAuth = true
) => {
  const token = requireAuth ? await getValidToken() : null;
  const headers = {
    'Content-Type': 'application/json',
    accept: 'application/json',
    Authorization: token ? `JWT ${token}` : '',
  };

  const request = { method, headers };
  if (body) {
    Object.defineProperty(request, 'body', { value: JSON.stringify(body) });
  }

  let response = await fetch(baseUrl + endpoint, request);
  if (response.status === 401) {
    const newToken = await getValidToken();
    request.headers.Authorization = `JWT ${newToken}`;
    response = await fetch(baseUrl + endpoint, request);
    if (response.status !== 200 && response.status === 401) {
      throw new Error('Auth Error');
    }
  }

  if (!response.ok) {
    throw new Error(
      `HTTP error! status: ${response.status} ${response.statusText}`
    );
  }

  if (method === 'DELETE') {
    return true;
  }
  const data = await response.json();
  return data;
};

const TrueApi = {
  login: async (email: string, password: string): Promise<TrueToken> => {
    try {
      console.log('Loggin in the api');
      const response = await executeRequest(
        'token/',
        'POST',
        {
          email,
          password,
        },
        false
      );

      console.log(response);
      chrome.storage.local.set({
        token: response.access,
        refresh: response.refresh,
      });

      return response;
    } catch (error) {
      // console.log(error);
      console.error(error);
      throw error;
    }
  },
  fetch_user_details: async (id: number): Promise<DetailResponse> => {
    const response = await executeRequest(`users/${id}/`, 'GET');

    console.log(response);

    return response;
  },
  add_to_cart: async (item: any, quantity: number): Promise<any> => {
    const payload = { ...item };
    payload.quantity = quantity;
    const response = await executeRequest(
      'extension/cart/add/',
      'POST',
      payload
    );
    console.log(response);
    return response;
  },
  delete_cart_item: async (item: CartItem): Promise<any> => {
    await executeRequest(`cart_item/${item.id}/`, 'DELETE');
    return true;
  },
  get_cart: async (): Promise<any> => {
    const response = await executeRequest('cart/get_user_cart/', 'GET');
    console.log('here is the cart response');
    console.log(response);
    return response;
  },
  query_item: async (
    name: string,
    partNumber: string,
    manufacturer?: string
  ): Promise<OfferItem> => {
    const payload: QueryPayload = {};
    if (name) payload.name = name;
    if (partNumber) payload.mfr_part = partNumber;
    if (manufacturer) payload.manufacturer = manufacturer;
    const response = await executeRequest(
      'bubba/bubbaparts/lookup/',
      'POST',
      { ...payload },
      false
    );
    return response[0];
  },
  query_by_part_number: async (partNumber: string): Promise<OfferItem> => {
    const payload: QueryPayload = {};
    payload.mfr_part = partNumber;
    const response = await executeRequest(
      'bubba/bubbaparts/lookup/',
      'POST',
      {
        ...payload,
      },
      false
    );
    return response[0];
  },
  query_by_name: async (name: string): Promise<OfferItem> => {
    const payload: QueryPayload = {};
    payload.name = name;
    const response = await executeRequest(
      'bubba/bubbaparts/namedlookup/',
      'POST',
      {
        ...payload,
      },
      false
    );
    console.log('here is the response from the name lookup');
    console.log(response);
    return response[0];
  },

  get_store_products: async (params?: string): Promise<any> => {
    let queryString = 'prices/';
    if (params) queryString += params;
    const response = await executeRequest(queryString, 'GET');
    console.log('here is the store response');
    console.log(response);
    return response;
  },
  // Add to src/services/TrueApi.ts
  check_part_exists: async (partNumber: string, asin: string, url: string): Promise<any> => {
    const response = await executeRequest(
      'bubba/bubbaparts/check_part_exists/',
      'POST',
      {
        mfr_part: partNumber,
        url: url,
        asin: asin
      }
    );
    return response;
  },
  create_amazon_affiliate_link: async(asin: string): Promise<any> => {
    const response = await executeRequest(
      'bubba/bubbaparts/create_amazon_affiliate/',  
      'POST',
      {
        asin: asin
      }
    );
    return response;
  },
  check_affiliate_status: async(taskId: string): Promise<any> => {
    const response = await executeRequest(
      'bubba/bubbaparts/check_affiliate_status/',
      'POST',
      {
        task_id: taskId
      }
    );
    return response;
  },
  create_part_with_affiliate: async (partData: any): Promise<any> => {
    const response = await executeRequest(
      'bubba/bubbaparts/create_from_amazon/',
      'POST',
      partData
    );
    return response;
  },
  get_item_details: async (itemId: string): Promise<any> => {
    const response = await executeRequest(
      `prices/${itemId}/get_details/`,
      'GET'
    );
    console.log('here is the details response');
    console.log(response);
    return response;
  },
  search_store_products: async (
    term: string,
    price?: number,
    link?: string
  ): Promise<any> => {
    console.log("Let's search the store");
    console.log(term);
    const requestBody: RequestBody = {
      term,
    };
    if (price) requestBody.price = price;
    if (link) requestBody.link = link;
    const response = await executeRequest(
      'prices/search/',
      'POST',
      requestBody
    );
    console.log('here are my serach results');
    console.log(response);
    return response;
  },
  search_store_products_by_name: async (
    term: string,
    price?: number,
    link?: string
  ): Promise<any> => {
    console.log("Let's search the store by name");
    console.log(term);
    const requestBody: RequestBody = {
      term,
    };
    if (price) requestBody.price = price;
    if (link) requestBody.link = link;
    const response = await executeRequest(
      'prices/search_by_name/',
      'POST',
      requestBody
    );
    console.log('here are my serach results');
    console.log(response);
    return response;
  },
};

export default TrueApi;
