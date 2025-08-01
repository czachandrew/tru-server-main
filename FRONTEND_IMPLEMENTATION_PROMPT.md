# 🎯 **Frontend Implementation Prompt: Referral System for Chrome Extension**

## 📋 **Project Overview**

You need to implement a **referral system** in the Chrome extension that allows users to share a portion of their affiliate earnings with organizations through unique referral codes. This is a **charitable giving feature** where users can support causes they care about while earning money.

---

## 🎯 **Core User Experience**

### **What Users Can Do:**
1. **Add Referral Codes**: Enter codes from organizations they want to support
2. **View Giving Dashboard**: See their charitable balance, giving history, and allocation percentages
3. **Adjust Allocations**: Modify how much goes to each organization (optional)
4. **Track Impact**: See total amount given and potential future giving
5. **Manage Codes**: Add/remove codes as their interests change

### **Key User Flows:**
1. **First Time Setup**: User enters a referral code → System validates → Code added → Allocations calculated
2. **Making Purchases**: User shops normally → Extension tracks purchases → Earnings automatically split → Organizations receive their share
3. **Managing Giving**: User views dashboard → Sees current allocations → Can add/remove codes → Real-time updates

---

## 🔧 **Technical Implementation**

### **Authentication**
All API calls require JWT authentication. Include the token in headers:
```javascript
const headers = {
  'Authorization': `Bearer ${userToken}`,
  'Content-Type': 'application/json'
};
```

### **GraphQL Endpoint**
Use the existing GraphQL endpoint: `https://your-api-domain.com/graphql/`

---

## 📊 **Required Features**

### **1. Referral Code Entry Modal**

**Location**: Add to the extension popup or settings page

**UI Components:**
- Input field for referral code (7+ characters, 2+ numbers)
- "Add Code" button
- Validation feedback (success/error messages)
- Loading state during validation

**Implementation:**
```javascript
// 1. Validate code before adding
const validateCode = async (code) => {
  const response = await graphqlClient.query({
    query: VALIDATE_REFERRAL_CODE,
    variables: { code }
  });
  return response.data.validateReferralCode;
};

// 2. Add code if valid
const addCode = async (code) => {
  const response = await graphqlClient.mutate({
    mutation: ADD_REFERRAL_CODE,
    variables: { input: { code } }
  });
  return response.data.addReferralCode;
};
```

**User Flow:**
1. User enters code → Show loading
2. Validate code → Show organization name if valid
3. User confirms → Add code → Show success message
4. Update dashboard with new allocations

### **2. Giving Dashboard**

**Location**: New tab in extension popup or dedicated page

**UI Components:**
- **Current Allocations**: Pie chart or percentage breakdown
- **Charitable Balance**: Total amount given to organizations
- **Potential Giving**: Amount from pending/projected earnings
- **Active Codes**: List of current referral codes with organization names
- **Giving History**: Recent transactions and amounts
- **Quick Actions**: Add/remove codes, view details

**Data Structure:**
```javascript
// Get comprehensive user summary
const getUserSummary = async () => {
  const response = await graphqlClient.query({
    query: GET_MY_REFERRAL_SUMMARY
  });
  return response.data.myReferralSummary;
};

// Example response structure:
{
  activeCodes: [
    {
      id: "1",
      referralCode: { code: "ABC1234" },
      allocationPercentage: "50.00",
      organizationName: "Test Church",
      promotionStatus: "Active (Code Entry Open)"
    }
  ],
  totalGiving: "15.00",
  potentialGiving: "15.00", 
  netEarnings: "15.00",
  userAllocationPercentage: "50.00",
  allocations: {
    user: 50.0,
    codes: { "1": 50.0 }
  }
}
```

### **3. Code Management**

**Features:**
- **View Active Codes**: List with organization names and percentages
- **Remove Codes**: Button to remove codes (with confirmation)
- **Allocation Display**: Show current split percentages
- **Status Indicators**: Show if codes are still active/valid

**Implementation:**
```javascript
// Remove a code
const removeCode = async (codeId) => {
  const response = await graphqlClient.mutate({
    mutation: REMOVE_REFERRAL_CODE,
    variables: { referralCodeId: codeId }
  });
  return response.data.removeReferralCode;
};
```

### **4. Giving History**

**Features:**
- **Transaction List**: Recent disbursements to organizations
- **Amount Details**: How much went to each organization
- **Date Tracking**: When transactions occurred
- **Status Indicators**: Pending, confirmed, paid status

**Implementation:**
```javascript
// Get giving history
const getGivingHistory = async () => {
  const response = await graphqlClient.query({
    query: GET_MY_REFERRAL_DISBURSEMENTS
  });
  return response.data.myReferralDisbursements;
};
```

---

## 🎨 **UI/UX Requirements**

### **Design Principles:**
- **Transparency**: Users should clearly see where their money goes
- **Simplicity**: Easy to understand allocation percentages
- **Trust**: Clear validation and confirmation steps
- **Impact**: Show the positive impact of their giving

### **Visual Elements:**
- **Progress Bars**: Show allocation percentages
- **Pie Charts**: Visual representation of earnings split
- **Icons**: Organization types (church, charity, etc.)
- **Color Coding**: Green for active, red for errors, blue for pending
- **Animations**: Smooth transitions when adding/removing codes

### **Responsive Design:**
- **Popup Mode**: Compact view for extension popup
- **Full Page**: Detailed view when opened in new tab
- **Mobile Friendly**: Works on mobile devices

---

## 🔄 **Real-time Updates**

### **Polling Strategy:**
- **After Code Changes**: Immediately refresh dashboard
- **After Purchases**: Poll every 30 seconds for 5 minutes
- **Background Updates**: Check for new earnings every 5 minutes
- **Manual Refresh**: Pull-to-refresh or refresh button

### **Implementation:**
```javascript
// Poll for updates after adding code
const pollForUpdates = (duration = 300000) => { // 5 minutes
  const interval = setInterval(async () => {
    const summary = await getUserSummary();
    updateDashboard(summary);
  }, 30000); // Every 30 seconds
  
  setTimeout(() => clearInterval(interval), duration);
};
```

---

## ⚠️ **Error Handling**

### **Common Scenarios:**
1. **Invalid Code**: Show specific error message
2. **Expired Promotion**: Explain timeline restrictions
3. **Already Added**: Prevent duplicate codes
4. **Network Errors**: Retry with exponential backoff
5. **Authentication**: Redirect to login if token expired

### **User-Friendly Messages:**
- ❌ "Code ABC1234 is not valid. Please check the code and try again."
- ❌ "This code has expired. Contact the organization for a new code."
- ❌ "You already have this code active."
- ✅ "Successfully added code for Test Church! 50% of your earnings will now go to this organization."

---

## 📱 **Chrome Extension Integration**

### **Storage:**
- **User Token**: Store JWT token securely
- **User Preferences**: Save dashboard preferences
- **Cache**: Cache user summary for offline viewing
- **Settings**: Remember user's preferred update frequency

### **Permissions:**
- **Storage**: For user preferences and cache
- **Active Tab**: For affiliate link detection
- **Background**: For polling updates

### **Background Script:**
```javascript
// Background script for polling
chrome.runtime.onStartup.addListener(() => {
  startPolling();
});

// Listen for purchase events
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'PURCHASE_DETECTED') {
    pollForUpdates();
  }
});
```

---

## 🧪 **Testing Requirements**

### **Manual Testing:**
1. **Add Valid Code**: Should show organization name and add successfully
2. **Add Invalid Code**: Should show specific error message
3. **Remove Code**: Should update allocations immediately
4. **Purchase Flow**: Should create disbursements automatically
5. **Real-time Updates**: Should reflect changes within 30 seconds

### **Test Data:**
- Use the manual testing script: `python manual_test_referral.py`
- Create test organizations and codes
- Simulate purchases to test disbursements

### **Edge Cases:**
- **No Codes**: Show 100% user allocation
- **Maximum Codes**: Prevent adding more than 5 codes
- **Expired Codes**: Show appropriate status
- **Network Issues**: Handle offline scenarios

---

## 📊 **Data Flow**

### **User Journey:**
1. **User enters code** → Validate → Show organization → Confirm → Add → Update allocations
2. **User makes purchase** → Extension detects → Create projected earning → Split automatically → Update dashboard
3. **User views dashboard** → Load summary → Display allocations → Show history → Enable actions

### **API Calls:**
1. **GET** `myReferralSummary` → Load dashboard data
2. **POST** `validateReferralCode` → Check code validity
3. **POST** `addReferralCode` → Add code to user
4. **POST** `removeReferralCode` → Remove code from user
5. **GET** `myReferralDisbursements` → Load giving history

---

## 🎯 **Success Metrics**

### **User Engagement:**
- **Code Addition Rate**: % of users who add at least one code
- **Active Codes**: Average number of codes per user
- **Dashboard Views**: How often users check their giving
- **Retention**: Users who keep codes active

### **Giving Impact:**
- **Total Amount Given**: Sum of all disbursements
- **Average Giving**: Per user giving amounts
- **Organization Reach**: Number of organizations supported
- **User Satisfaction**: Feedback on the feature

---

## 🚀 **Implementation Priority**

### **Phase 1 (MVP):**
1. **Code Entry Modal**: Basic add code functionality
2. **Simple Dashboard**: Show allocations and giving amounts
3. **Basic Validation**: Error handling for invalid codes
4. **Real-time Updates**: Poll for changes after actions

### **Phase 2 (Enhanced):**
1. **Giving History**: Detailed transaction list
2. **Code Management**: Remove codes and view details
3. **Advanced UI**: Charts and visualizations
4. **Offline Support**: Cache and offline functionality

### **Phase 3 (Polish):**
1. **Custom Allocations**: User-defined percentages
2. **Notifications**: Earnings and giving alerts
3. **Social Features**: Share giving impact
4. **Analytics**: Detailed user insights

---

## 📞 **Support & Resources**

### **Documentation:**
- **API Documentation**: `REFERRAL_API_DOCUMENTATION.md`
- **GraphQL Schema**: Available at `/graphql/` endpoint
- **Testing Scripts**: `manual_test_referral.py` and `test_referral_shell.py`

### **Backend Team:**
- **API Issues**: Check GraphQL schema and error responses
- **Data Problems**: Verify with testing scripts
- **Performance**: Monitor polling frequency and cache usage

### **Testing Environment:**
- **Dev Database**: Safe to create test data
- **Manual Testing**: Use provided scripts
- **Error Logging**: Check browser console and network tab

---

## 🎉 **Expected Outcome**

After implementation, users should be able to:
- ✅ **Easily add referral codes** from organizations they support
- ✅ **See their giving impact** in real-time
- ✅ **Manage their charitable allocations** transparently
- ✅ **Track their giving history** and total impact
- ✅ **Feel confident** that their earnings are being shared correctly

**The goal is to make charitable giving seamless and transparent, encouraging users to support causes they care about while earning money through the affiliate system.**

---

**🎯 Ready to implement? Start with the code entry modal and basic dashboard, then iterate based on user feedback!** 