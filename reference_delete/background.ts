import { FoundProduct, TruProduct } from '@/stores/types.d';
import TrueGraphQLApi from '@/services/TrueApiGraph';
import Messages from './Messages';

console.log('hello world background todo something~');

function updateTrueStore(message: string, status = 'waiting') {
  console.log('I am updating the store in the background');
  chrome.storage.local.get(['tru_state'], result => {
    console.log('Here is the result of the get');
    console.log(result);
    const truStore = result.tru_state;
    truStore.message = message;
    truStore.showOnOpen = true;
    truStore.status = status;
    chrome.storage.local.set({ tru_state: truStore });
  });
}

chrome.runtime.onMessage.addListener(async (message, sender, sendResponse) => {
  console.log(message);
  console.log(sender);
  if (message.subject === Messages.LOOKUP) {
    const productName = message.query.name;
    const mfrPart = message.query.mfr_part;
    const url = message.query.link;
    const asin = message.query.asin;
    chrome.storage.local.set({ examinedItem: message.query as FoundProduct });
    
    let result;
    console.log('Here is the sender tab when we are sending from an imported script');
    console.log(sender.tab?.id);
    
    // First check if part already exists
    if (mfrPart !== '') {
      try {
        const partExists = await TrueGraphQLApi.check_part_exists(mfrPart, asin, url);
        
        if (!partExists || !partExists.exists) {
          // Create part with affiliate link if it doesn't exist
          console.log('Part not found, creating with affiliate link');
          const createPartResponse = await TrueGraphQLApi.create_part_with_affiliate({
            name: productName,
            description: productName || '',
            partNumber: mfrPart || `ASIN-${asin}`,
            manufacturer: message.query.manufacturer || '',
            asin: asin,
            url: url,
            image: message.query.image || '',
            category: message.query.categories?.[0] || ''
          });
          
          console.log('Part created successfully:', createPartResponse);
          
          // Could store the newly created part info if needed
          chrome.storage.local.set({ 
            createdPart: createPartResponse 
          });
        } else {
          console.log('Part already exists in database:', partExists);
        }
      } catch (error) {
        console.error('Error in part existence check or creation:', error);
      }
    }
    
    // Now proceed with regular search as before
    if (mfrPart === '') {
      console.log('searching by name');
      result = await TrueGraphQLApi.search_store_products_by_name(
        productName,
        message.query.price,
        message.query.link
      );
    } else {
      result = await TrueGraphQLApi.search_store_products(
        message.query.mfr_part,
        message.query.price,
        message.query.link
      );
    }
    console.log('here is what we have for results');
    console.log(result);
    if (result && result.length > 0) {
      chrome.storage.local.set({ foundItem: result[0] as TruProduct });
      // here we should set the message as I foudn it! and immediately start the comparison method to generate the next method
      updateTrueStore('I found this product, let me compare it for you');
      chrome.tabs.sendMessage(sender.tab?.id ? sender.tab.id : 1, {
        subject: Messages.SHOW_BUTTON,
        payload: result[0],
      });
    } else {
      chrome.storage.local.set({ foundItem: null });
      // here we woudl set the message in the store as I'm looking for an alternative product that i have a TruePrice for
      updateTrueStore(
        "I don't currently have a TruePrice for this product, but I'm looking for an alternative",
        'Finding a similar product'
      );
    }

    // chrome.tabs.sendMessage(sender.tab?.id ? sender.tab.id : 1, result[0]);
  }

  if (message.subject === Messages.ADD_TO_CART) {
    // here we are going to need to add
    console.log('Ok I have the add to cart message');
    console.log(message);
    const response = await TrueGraphQLApi.add_to_cart(message.item.id, message.quantity);
    console.log('Here is the add to cart response');
    // chrome.storage.local.set({ cart_item: message.item });
    sendResponse(response);
  }

  return true;
});
