# 🎯 **Referral System API Documentation**

## 📋 **Overview**

The Referral System allows users to share a portion of their affiliate earnings with organizations through unique referral codes. This system includes:

- **User Code Management**: Add/remove referral codes with automatic allocation calculation
- **Organization Management**: Create organizations and promotions
- **Purchase Integration**: Automatic disbursement creation on purchases
- **Real-time Tracking**: Live allocation and earnings updates

---

## 🔐 **Authentication**

All referral system endpoints require authentication. Include the JWT token in the Authorization header:

```graphql
# Headers
{
  "Authorization": "Bearer <your-jwt-token>"
}
```

---

## 📊 **Core Concepts**

### **Allocation System**
- **Equal Distribution**: When users add codes, earnings are split equally among all active codes + user's share
- **Example**: 1 code = 50% user, 50% organization | 2 codes = 33.33% each | 3 codes = 25% each
- **Transaction Immutability**: Allocations are locked at purchase time and don't change if codes are modified later

### **Promotion Timeline**
- **Code Entry Period**: 30 days from promotion start (users can add codes)
- **Purchase Period**: 60 days from promotion start (purchases count for earnings)
- **Active Status**: Only active promotions within timeline are valid

---

## 🔍 **Queries**

### **1. User Referral Summary**

Get comprehensive user referral activity including active codes, giving statistics, and allocations.

```graphql
query GetMyReferralSummary {
  myReferralSummary {
    activeCodes {
      id
      referralCode {
        code
        owner {
          profile {
            organizationName
          }
        }
      }
      allocationPercentage
      isActive
      addedAt
      organizationName
      promotionStatus
    }
    totalGiving
    potentialGiving
    netEarnings
    potentialNetEarnings
    userAllocationPercentage
    allocations
  }
}
```

**Response Example:**
```json
{
  "data": {
    "myReferralSummary": {
      "activeCodes": [
        {
          "id": "1",
          "referralCode": {
            "code": "ABC1234",
            "owner": {
              "profile": {
                "organizationName": "Test Church"
              }
            }
          },
          "allocationPercentage": "50.00",
          "isActive": true,
          "addedAt": "2024-01-15T10:30:00Z",
          "organizationName": "Test Church",
          "promotionStatus": "Active (Code Entry Open)"
        }
      ],
      "totalGiving": "15.00",
      "potentialGiving": "15.00",
      "netEarnings": "15.00",
      "potentialNetEarnings": "30.00",
      "userAllocationPercentage": "50.00",
      "allocations": {
        "user": 50.0,
        "codes": {
          "1": 50.0
        }
      }
    }
  }
}
```

### **2. User's Active Referral Codes**

Get list of user's active referral codes.

```graphql
query GetMyReferralCodes {
  myReferralCodes {
    id
    referralCode {
      code
      owner {
        profile {
          organizationName
        }
      }
    }
    allocationPercentage
    isActive
    addedAt
    organizationName
    promotionStatus
  }
}
```

### **3. User's Giving History**

Get detailed history of user's referral disbursements.

```graphql
query GetMyReferralDisbursements {
  myReferralDisbursements {
    id
    amount
    allocationPercentage
    status
    createdAt
    organizationName
    referralCode {
      code
    }
    recipientUser {
      profile {
        organizationName
      }
    }
  }
}
```

### **4. Validate Referral Code**

Validate a referral code before adding it.

```graphql
query ValidateReferralCode($code: String!) {
  validateReferralCode(code: $code) {
    isValid
    message
    referralCode {
      code
      owner {
        profile {
          organizationName
        }
      }
    }
    organizationName
  }
}
```

**Variables:**
```json
{
  "code": "ABC1234"
}
```

**Response Examples:**

✅ **Valid Code:**
```json
{
  "data": {
    "validateReferralCode": {
      "isValid": true,
      "message": "Code is valid",
      "referralCode": {
        "code": "ABC1234",
        "owner": {
          "profile": {
            "organizationName": "Test Church"
          }
        }
      },
      "organizationName": "Test Church"
    }
  }
}
```

❌ **Invalid Code:**
```json
{
  "data": {
    "validateReferralCode": {
      "isValid": false,
      "message": "Code entry period has ended for this promotion",
      "referralCode": null,
      "organizationName": null
    }
  }
}
```

### **5. Organization Summary**

Get organization's referral activity summary (requires organization ID).

```graphql
query GetOrganizationSummary($organizationId: ID!) {
  organizationSummary(organizationId: $organizationId) {
    activePromotions
    totalReceived
    pendingDisbursements
    verificationStatus
  }
}
```

### **6. Public Referral Codes**

Get all active referral codes (public information only).

```graphql
query GetPublicReferralCodes {
  publicReferralCodes {
    code
    isActive
    isValid
    promotionStatus
    owner {
      profile {
        organizationName
      }
    }
  }
}
```

---

## ✏️ **Mutations**

### **1. Add Referral Code**

Add a referral code to the current user's active codes.

```graphql
mutation AddReferralCode($input: ReferralCodeInput!) {
  addReferralCode(input: $input) {
    success
    message
    userReferralCode {
      id
      referralCode {
        code
        owner {
          profile {
            organizationName
          }
        }
      }
      allocationPercentage
      isActive
      addedAt
    }
    newAllocations
  }
}
```

**Variables:**
```json
{
  "input": {
    "code": "ABC1234",
    "allocationPercentage": null  // Optional: custom allocation
  }
}
```

**Response Example:**
```json
{
  "data": {
    "addReferralCode": {
      "success": true,
      "message": "Successfully added referral code ABC1234",
      "userReferralCode": {
        "id": "1",
        "referralCode": {
          "code": "ABC1234",
          "owner": {
            "profile": {
              "organizationName": "Test Church"
            }
          }
        },
        "allocationPercentage": "50.00",
        "isActive": true,
        "addedAt": "2024-01-15T10:30:00Z"
      },
      "newAllocations": {
        "user": 50.0,
        "codes": {
          "1": 50.0
        }
      }
    }
  }
}
```

### **2. Remove Referral Code**

Remove a referral code from the current user's active codes.

```graphql
mutation RemoveReferralCode($referralCodeId: ID!) {
  removeReferralCode(referralCodeId: $referralCodeId) {
    success
    message
    newAllocations
  }
}
```

**Variables:**
```json
{
  "referralCodeId": "1"
}
```

### **3. Create Organization**

Create a new organization account.

```graphql
mutation CreateOrganization($input: CreateOrganizationInput!) {
  createOrganization(input: $input) {
    success
    message
    organization {
      id
      email
      profile {
        organizationName
        organizationType
        isOrganization
        minPayoutAmount
      }
    }
  }
}
```

**Variables:**
```json
{
  "input": {
    "email": "church@example.com",
    "password": "securepassword123",
    "organizationName": "Test Church",
    "organizationType": "church",
    "minPayoutAmount": "10.00"
  }
}
```

### **4. Create Promotion**

Create a new promotion for an organization.

```graphql
mutation CreatePromotion($input: CreatePromotionInput!) {
  createPromotion(input: $input) {
    success
    message
    promotion {
      id
      startDate
      codeEntryDeadline
      endDate
      isActive
      status
    }
    referralCode {
      code
      isActive
    }
  }
}
```

**Variables:**
```json
{
  "input": {
    "organizationId": "1",
    "startDate": "2024-01-15T00:00:00Z",
    "isActive": true,
    "customCode": "CHURCH2024"  // Optional: custom code
  }
}
```

### **5. Validate Referral Code (Mutation)**

Alternative validation endpoint as a mutation.

```graphql
mutation ValidateReferralCode($code: String!) {
  validateReferralCode(code: $code) {
    success
    message
    isValid
    referralCode {
      code
      owner {
        profile {
          organizationName
        }
      }
    }
    organizationName
  }
}
```

---

## 🎯 **Frontend Integration Examples**

### **Complete User Workflow**

```javascript
// 1. Get user's current referral summary
const summary = await graphqlClient.query({
  query: GET_MY_REFERRAL_SUMMARY
});

// 2. Validate a code before adding
const validation = await graphqlClient.query({
  query: VALIDATE_REFERRAL_CODE,
  variables: { code: "ABC1234" }
});

if (validation.data.validateReferralCode.isValid) {
  // 3. Add the code
  const result = await graphqlClient.mutate({
    mutation: ADD_REFERRAL_CODE,
    variables: { input: { code: "ABC1234" } }
  });
  
  // 4. Update UI with new allocations
  updateAllocations(result.data.addReferralCode.newAllocations);
}
```

### **Organization Dashboard**

```javascript
// Get organization summary
const orgSummary = await graphqlClient.query({
  query: GET_ORGANIZATION_SUMMARY,
  variables: { organizationId: "1" }
});

// Display earnings and user counts
const { totalReceived, pendingDisbursements, activePromotions } = orgSummary.data.organizationSummary;
```

### **Real-time Updates**

```javascript
// Poll for updates after purchases
setInterval(async () => {
  const summary = await graphqlClient.query({
    query: GET_MY_REFERRAL_SUMMARY
  });
  
  // Update UI with new giving amounts
  updateGivingDisplay(summary.data.myReferralSummary);
}, 30000); // Every 30 seconds
```

---

## ⚠️ **Error Handling**

### **Common Error Responses**

```json
{
  "errors": [
    {
      "message": "Authentication required",
      "extensions": {
        "code": "UNAUTHENTICATED"
      }
    }
  ]
}
```

```json
{
  "data": {
    "addReferralCode": {
      "success": false,
      "message": "Code entry period has ended for this promotion",
      "userReferralCode": null,
      "newAllocations": null
    }
  }
}
```

### **Validation Errors**

- **Invalid Code Format**: "Code must be at least 7 characters"
- **Code Not Found**: "Invalid or inactive referral code"
- **Expired Promotion**: "Code entry period has ended for this promotion"
- **Already Added**: "You already have this code active"
- **Too Many Codes**: "Maximum 5 active codes allowed"

---

## 🔧 **Testing**

### **Test Queries**

```bash
# Test user summary
curl -X POST http://localhost:8000/graphql/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { myReferralSummary { totalGiving potentialGiving userAllocationPercentage } }"}'

# Test code validation
curl -X POST http://localhost:8000/graphql/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { validateReferralCode(code: \"ABC1234\") { isValid message } }"}'
```

### **Manual Testing Script**

```bash
# Run the comprehensive test
python manual_test_referral.py

# Or use interactive shell
python manage.py shell
exec(open('test_referral_shell.py').read())
```

---

## 📈 **Performance Considerations**

- **Caching**: User summaries are calculated on-demand, consider caching for high-traffic scenarios
- **Batch Operations**: Use `myReferralSummary` for comprehensive data instead of multiple queries
- **Real-time Updates**: Poll every 30-60 seconds for live updates
- **Error Handling**: Always check `success` field in mutation responses

---

## 🔄 **Data Flow**

1. **User adds referral code** → Allocation recalculated → Future purchases affected
2. **Purchase occurs** → Commission calculated → Disbursements created (immutable)
3. **User removes code** → Allocation recalculated → Future purchases affected
4. **Organization receives** → Pending disbursements → Admin processes payouts

---

## 📞 **Support**

For API issues or questions:
- Check GraphQL schema introspection at `/graphql/`
- Review server logs for detailed error messages
- Test with the provided manual testing scripts
- Verify authentication and permissions

---

**🎉 The referral system is now fully integrated and ready for frontend development!** 