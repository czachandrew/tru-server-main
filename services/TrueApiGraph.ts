        } else if (item.isAlternative === true || item.relationshipType === 'equivalent') {
          // Alternative products (competing items)
          if (item.offers && item.offers.length > 0) {
            item.offers.forEach((offer: any) => {
              const vendorName = offer.vendor && typeof offer.vendor === 'object'
                ? offer.vendor.name
                : null;
              const offerPrice = parseFloat(offer.sellingPrice) || 0;
              
              if (offerPrice > 0) {
                const productName = offer.productName || item.name || item.title;
                const productPartNumber = offer.productPartNumber || item.partNumber;
                const productImage = offer.productImage || item.mainImage;
                
                console.log(`🔄 Alternative Product: ${productName} (${productPartNumber}), Price: $${offerPrice}, Vendor: ${vendorName}, Margin: ${item.marginOpportunity}`);
                
                alternativeProducts.push({
                  isAmazonProduct: item.isAmazonProduct,
                  isAlternative: item.isAlternative,
                  relationshipType: item.relationshipType,
                  relationshipCategory: item.relationshipCategory,
                  marginOpportunity: item.marginOpportunity,
                  revenueType: item.revenueType,
                  matchType: item.matchType,
                  matchConfidence: item.matchConfidence,
                  product: {
                    id: `${item.id}-${offer.id}`,
                    name: productName,
                    title: productName,
                    partNumber: productPartNumber,
                    asin: item.asin || productIdentifiers.asin || '',
                    mainImage: productImage,
                    image_url: productImage,
                    description: item.description,
                    manufacturer: manufacturerName,
                    price: item.price,
                    affiliateLinks: [],
                    offers: [offer],
                    isAmazonProduct: item.isAmazonProduct,
                    isAlternative: item.isAlternative,
                    relationshipType: item.relationshipType,
                    relationshipCategory: item.relationshipCategory,
                    marginOpportunity: item.marginOpportunity,
                    revenueType: item.revenueType,
                    matchType: item.matchType,
                    matchConfidence: item.matchConfidence
                  },
                  id: `${item.id}-${offer.id}`,
                  name: productName,
                  title: productName,
                  amount: offerPrice,
                  vendor: vendorName,
                  image: productImage,
                  image_url: productImage,
                  partNumber: productPartNumber,
                  offers: [offer],
                  affiliateLinks: []
                });
              }
            });
          } else {
            // DEMO PRODUCTS: Include alternatives without offers (like demo products)
            const productName = item.name || item.title;
            const productPartNumber = item.partNumber;
            const productImage = item.mainImage;
            
            console.log(`🎯 Demo Alternative Product: ${productName} (${productPartNumber}), Type: ${item.relationshipType}, Category: ${item.relationshipCategory}`);
            
            alternativeProducts.push({
              isAmazonProduct: item.isAmazonProduct,
              isAlternative: item.isAlternative,
              relationshipType: item.relationshipType,
              relationshipCategory: item.relationshipCategory,
              marginOpportunity: item.marginOpportunity,
              revenueType: item.revenueType,
              matchType: item.matchType,
              matchConfidence: item.matchConfidence,
              product: {
                id: item.id,
                name: productName,
                title: productName,
                partNumber: productPartNumber,
                asin: item.asin || productIdentifiers.asin || '',
                mainImage: productImage,
                image_url: productImage,
                description: item.description,
                manufacturer: manufacturerName,
                price: item.price || "Demo Product",
                affiliateLinks: [],
                offers: [],
                isAmazonProduct: item.isAmazonProduct,
                isAlternative: item.isAlternative,
                relationshipType: item.relationshipType,
                relationshipCategory: item.relationshipCategory,
                marginOpportunity: item.marginOpportunity,
                revenueType: item.revenueType,
                matchType: item.matchType,
                matchConfidence: item.matchConfidence
              },
              id: item.id,
              name: productName,
              title: productName,
              amount: 0, // Demo products have no price
              vendor: "Demo Product",
              image: productImage,
              image_url: productImage,
              partNumber: productPartNumber,
              offers: [],
              affiliateLinks: []
            });
          }
        } 