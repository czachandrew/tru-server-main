# Demo TruPrice Feature - Virtual Superior Offers

## 🎯 **Feature Overview**

When a quote is uploaded with **demo mode enabled**, the system automatically generates virtual "TruPrice" offers for every quote item that shows 5-10% better pricing than the quoted prices. These virtual offers demonstrate competitive threats to reseller partners without creating actual database records.

## 🔧 **How It Works**

### **1. Demo Mode Detection**
When a quote is processed with `demoMode=true`:
- Quote is marked with `demo_mode_enabled=true`
- Virtual TruPrice offers are generated on-the-fly during GraphQL queries
- No additional database records are created

### **2. Virtual Offer Generation**
For each quote item in demo mode:
- **Discount**: Random 5-10% reduction from quote price
- **Vendor**: Virtual "TruPrice" supplier (code: `TRUPRICE`)
- **Pricing**: Always better than quote pricing
- **Status**: Marked as confirmed and in-stock

### **3. GraphQL Integration**
Virtual offers appear seamlessly in product queries:
- Mixed with real offers in the `offers` array
- Formatted exactly like database offers
- Include all standard offer fields

## 📊 **Demo Experience**

### **Quote Upload**
```javascript
// Frontend uploads with demo flag
const formData = new FormData();
formData.append('file', pdfFile);
formData.append('demoMode', 'true');  // 🎯 Enables TruPrice offers

fetch('/upload-quote/', {
  method: 'POST',
  headers: { 'Authorization': `JWT ${token}` },
  body: formData
});
```

### **GraphQL Response**
```json
{
  "quote": {
    "items": [
      {
        "partNumber": "DS1621XS+",
        "unitPrice": "1445.85",
        "matches": [
          {
            "product": {
              "offers": [
                {
                  "id": "123",
                  "sellingPrice": "1445.85",
                  "offerType": "QUOTE", 
                  "isConfirmed": false,
                  "vendor": {
                    "name": "CDW Technology Solutions",
                    "code": "CDW"
                  }
                },
                {
                  "id": "virtual_truprice_456_789",
                  "sellingPrice": "1347.23",    // 6.8% better!
                  "offerType": "SUPPLIER",
                  "isConfirmed": true,
                  "vendor": {
                    "name": "TruPrice",           // 🎯 Virtual vendor
                    "code": "TRUPRICE"
                  }
                }
              ]
            }
          }
        ]
      }
    ]
  }
}
```

## 💡 **Demo Impact**

### **Visual Comparison**
```
Original Quote:  $1,445.85 (CDW)
TruPrice Offer:  $1,347.23 (6.8% savings)
Customer Saves:  $98.62 per unit
```

### **Reseller Partner Demo Script**
1. **Upload competitor quote** with demo mode enabled
2. **Show processing** with real-time progress
3. **Reveal results** highlighting TruPrice offers
4. **Calculate total savings** across all line items
5. **Demonstrate threat**: "Your customers can get better pricing elsewhere"

## 🏗️ **Technical Implementation**

### **Virtual Offer Creation**
```python
def _create_virtual_offer(self, product, price, quote_item, discount_percent):
    """Create a virtual offer object that looks like a real one"""
    
    # Create virtual offer (don't save to database)
    virtual_offer = Offer(
        id=f"virtual_truprice_{product.id}_{quote_item.id}",
        product=product,
        vendor=truprice_vendor,
        offer_type='supplier',
        selling_price=Decimal(str(round(price, 2))),
        vendor_sku=f"TP-{quote_item.part_number}",
        stock_quantity=quote_item.quantity,
        is_in_stock=True,
        is_active=True,
        is_confirmed=True,  # TruPrice is always confirmed
        source_quote=None
    )
    
    # Add metadata for identification
    virtual_offer._is_virtual = True
    virtual_offer._discount_percent = discount_percent
    virtual_offer._original_price = quote_item.unit_price
    
    return virtual_offer
```

### **Demo Context Injection**
```python
def resolve_quote(self, info, id):
    quote = Quote.objects.get(id=id)
    
    # Inject demo context for virtual offers
    if quote.demo_mode_enabled:
        info.context._demo_quote_context = {
            'demo_mode': True,
            'quote': quote,
            'quote_items': quote.items.all()
        }
    
    return quote
```

### **Dynamic Offer Resolution**
```python
def resolve_offers(self, info):
    real_offers = list(self.offers.all())
    
    # Check for demo context
    demo_context = getattr(info.context, '_demo_quote_context', None)
    
    if demo_context and demo_context.get('demo_mode'):
        # Generate virtual TruPrice offers
        virtual_offers = self._generate_virtual_truprice_offers(demo_context)
        return real_offers + virtual_offers
    
    return real_offers
```

## 🎨 **Frontend Display**

### **Offer Comparison Component**
```javascript
const OfferComparison = ({ offers, quotePrice }) => {
  const trupriceOffer = offers.find(o => o.vendor.code === 'TRUPRICE');
  const savings = quotePrice - trupriceOffer?.sellingPrice || 0;
  const savingsPercent = (savings / quotePrice * 100).toFixed(1);

  return (
    <div className="offer-comparison">
      <div className="quote-price">
        <span>Quote Price: ${quotePrice}</span>
      </div>
      
      {trupriceOffer && (
        <div className="truprice-offer highlight">
          <span>TruPrice: ${trupriceOffer.sellingPrice}</span>
          <badge className="savings">
            Save ${savings.toFixed(2)} ({savingsPercent}%)
          </badge>
        </div>
      )}
    </div>
  );
};
```

### **Competitive Threat Visualization**
```javascript
const CompetitiveThreat = ({ quotes }) => {
  const totalSavings = quotes.reduce((sum, quote) => {
    return sum + quote.items.reduce((itemSum, item) => {
      const trupriceOffer = item.matches[0]?.product?.offers
        ?.find(o => o.vendor.code === 'TRUPRICE');
      if (trupriceOffer) {
        return itemSum + (item.unitPrice - trupriceOffer.sellingPrice) * item.quantity;
      }
      return itemSum;
    }, 0);
  }, 0);

  return (
    <div className="threat-summary">
      <h2>⚠️ Competitive Risk Analysis</h2>
      <div className="total-exposure">
        <span>Total Customer Savings Available:</span>
        <span className="amount">${totalSavings.toFixed(2)}</span>
      </div>
      <div className="threat-level">
        <span>Risk Level: </span>
        <badge className="high-risk">HIGH</badge>
      </div>
    </div>
  );
};
```

## 🚀 **Benefits for Demos**

### **1. Immediate Impact**
- **Visual proof** of pricing vulnerabilities
- **Quantified savings** customers could achieve
- **Professional presentation** with real data
- **No manual data entry** required

### **2. Realistic Demonstration**
- **Believable pricing** (5-10% improvements)
- **Consistent branding** with TruPrice vendor
- **Seamless integration** with real offers
- **Automated generation** for any quote

### **3. Sales Conversation Starters**
- "Your customers can save X% by shopping elsewhere"
- "Here's what you're competing against"
- "TruPrice shows the market reality"
- "How will you respond to this pricing pressure?"

## 📋 **Usage Instructions**

### **For Sales Demos**
1. **Enable demo mode** when uploading competitor quotes
2. **Wait for processing** to complete (shows professional progress)
3. **Display results** highlighting TruPrice offers
4. **Focus on savings** and competitive threats
5. **Position solution** as protecting against price erosion

### **For Development Testing**
1. Upload any PDF quote with `demoMode=true`
2. Query the quote via GraphQL after processing
3. Verify virtual TruPrice offers appear in product offers
4. Confirm pricing is 5-10% better than quote prices
5. Test that virtual offers don't persist in database

## ⚡ **Performance Notes**

- **Zero database impact**: Virtual offers are generated in memory
- **Fast generation**: Simple math operations on existing data
- **Scalable**: Works with quotes of any size
- **Cache-friendly**: Virtual offers computed on each request
- **Clean separation**: Demo logic isolated from production data

This feature provides a powerful demonstration tool that shows reseller partners exactly what competitive threats they face, using their own quote data as the foundation for compelling visualizations! 🎯
