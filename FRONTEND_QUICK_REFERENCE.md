# 🚀 **Frontend Quick Reference: Referral System**

## 📋 **Essential GraphQL Queries & Mutations**

### **🔍 Core Queries**

#### **1. Get User Summary (Main Dashboard)**
```graphql
query GetMyReferralSummary {
  myReferralSummary {
    activeCodes {
      id
      referralCode { code }
      allocationPercentage
      organizationName
      promotionStatus
    }
    totalGiving
    potentialGiving
    netEarnings
    userAllocationPercentage
    allocations
  }
}
```

#### **2. Validate Referral Code**
```graphql
query ValidateReferralCode($code: String!) {
  validateReferralCode(code: $code) {
    isValid
    message
    organizationName
  }
}
```

#### **3. Get Giving History**
```graphql
query GetMyReferralDisbursements {
  myReferralDisbursements {
    id
    amount
    allocationPercentage
    status
    createdAt
    organizationName
  }
}
```

### **✏️ Core Mutations**

#### **1. Add Referral Code**
```graphql
mutation AddReferralCode($input: ReferralCodeInput!) {
  addReferralCode(input: $input) {
    success
    message
    newAllocations
  }
}
```

#### **2. Remove Referral Code**
```graphql
mutation RemoveReferralCode($referralCodeId: ID!) {
  removeReferralCode(referralCodeId: $referralCodeId) {
    success
    message
    newAllocations
  }
}
```

---

## 🎯 **Implementation Checklist**

### **Phase 1: MVP Features**
- [ ] **Code Entry Modal**
  - [ ] Input field with validation
  - [ ] Validate code before adding
  - [ ] Show organization name
  - [ ] Success/error messages
- [ ] **Basic Dashboard**
  - [ ] Show allocation percentages
  - [ ] Display total giving amount
  - [ ] List active codes
  - [ ] Real-time updates

### **Phase 2: Enhanced Features**
- [ ] **Giving History**
  - [ ] Transaction list
  - [ ] Amount details
  - [ ] Date tracking
- [ ] **Code Management**
  - [ ] Remove codes
  - [ ] Status indicators
  - [ ] Confirmation dialogs

---

## 🔧 **JavaScript Implementation Examples**

### **Add Code Flow**
```javascript
const addReferralCode = async (code) => {
  try {
    // 1. Validate code
    const validation = await graphqlClient.query({
      query: VALIDATE_REFERRAL_CODE,
      variables: { code }
    });
    
    if (!validation.data.validateReferralCode.isValid) {
      throw new Error(validation.data.validateReferralCode.message);
    }
    
    // 2. Add code
    const result = await graphqlClient.mutate({
      mutation: ADD_REFERRAL_CODE,
      variables: { input: { code } }
    });
    
    if (result.data.addReferralCode.success) {
      // 3. Update dashboard
      updateDashboard(result.data.addReferralCode.newAllocations);
      showSuccess(result.data.addReferralCode.message);
    }
  } catch (error) {
    showError(error.message);
  }
};
```

### **Dashboard Updates**
```javascript
const updateDashboard = async () => {
  try {
    const summary = await graphqlClient.query({
      query: GET_MY_REFERRAL_SUMMARY
    });
    
    const data = summary.data.myReferralSummary;
    
    // Update UI elements
    updateAllocationChart(data.allocations);
    updateGivingAmounts(data.totalGiving, data.potentialGiving);
    updateActiveCodes(data.activeCodes);
    
  } catch (error) {
    console.error('Dashboard update failed:', error);
  }
};
```

### **Real-time Polling**
```javascript
const startPolling = (duration = 300000) => { // 5 minutes
  const interval = setInterval(updateDashboard, 30000); // Every 30 seconds
  setTimeout(() => clearInterval(interval), duration);
};

// Start polling after user actions
const onCodeAdded = () => {
  updateDashboard(); // Immediate update
  startPolling(); // Then poll for changes
};
```

---

## 📊 **Data Structures**

### **User Summary Response**
```javascript
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

### **Validation Response**
```javascript
// Success
{
  isValid: true,
  message: "Code is valid",
  organizationName: "Test Church"
}

// Error
{
  isValid: false,
  message: "Code entry period has ended for this promotion",
  organizationName: null
}
```

---

## ⚠️ **Error Handling**

### **Common Error Messages**
- `"Code must be at least 7 characters"`
- `"Code must contain at least 2 numbers"`
- `"Invalid or inactive referral code"`
- `"Code entry period has ended for this promotion"`
- `"You already have this code active"`
- `"Authentication required"`

### **Error Handling Pattern**
```javascript
const handleGraphQLError = (error) => {
  if (error.message.includes('Authentication')) {
    redirectToLogin();
  } else if (error.message.includes('Network')) {
    showOfflineMessage();
  } else {
    showUserFriendlyError(error.message);
  }
};
```

---

## 🎨 **UI Components**

### **Allocation Display**
```javascript
const renderAllocationChart = (allocations) => {
  const { user, codes } = allocations;
  
  return `
    <div class="allocation-chart">
      <div class="user-share" style="width: ${user}%">
        You: ${user}%
      </div>
      ${Object.entries(codes).map(([id, percentage]) => `
        <div class="org-share" style="width: ${percentage}%">
          ${getOrgName(id)}: ${percentage}%
        </div>
      `).join('')}
    </div>
  `;
};
```

### **Code List**
```javascript
const renderActiveCodes = (codes) => {
  return codes.map(code => `
    <div class="code-item">
      <span class="code">${code.referralCode.code}</span>
      <span class="org">${code.organizationName}</span>
      <span class="percentage">${code.allocationPercentage}%</span>
      <button onclick="removeCode('${code.id}')">Remove</button>
    </div>
  `).join('');
};
```

---

## 🧪 **Testing**

### **Quick Test Queries**
```bash
# Test user summary
curl -X POST http://localhost:8000/graphql/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { myReferralSummary { totalGiving userAllocationPercentage } }"}'

# Test code validation
curl -X POST http://localhost:8000/graphql/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { validateReferralCode(code: \"ABC1234\") { isValid message } }"}'
```

### **Test Data Creation**
```bash
# Run manual test script
python manual_test_referral.py

# Or use interactive shell
python manage.py shell
exec(open('test_referral_shell.py').read())
```

---

## 📞 **Support**

- **API Issues**: Check `REFERRAL_API_DOCUMENTATION.md`
- **Testing**: Use `manual_test_referral.py`
- **Schema**: Visit `/graphql/` endpoint
- **Backend Team**: For data or logic issues

---

**🎯 Start with the code entry modal and basic dashboard, then build from there!** 