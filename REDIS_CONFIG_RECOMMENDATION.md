# Redis Configuration for Django + Puppeteer Worker

## Current Status ✅

Your Django side is working correctly! The test shows:

- **Django Redis Config**: localhost:6379 (local development)
- **Pub/Sub Working**: 2 subscribers notified 
- **Search Tasks**: Successfully generated and published
- **Consistency**: Both `affiliates/tasks.py` and `schema.py` use identical Redis config

## The Issue 🎯

Your **Puppeteer worker** needs to use the **exact same Redis configuration logic** as Django.

## Recommended Puppeteer Worker Redis Config

### Current Django Logic (WORKING):
```javascript
// In your Puppeteer worker, replace your Redis config with this:

function getRedisConfig() {
    // Check for development mode or local Redis first
    if (process.env.NODE_ENV === 'development' || process.env.USE_LOCAL_REDIS === 'true') {
        console.log("🔧 Using local Redis for development");
        return {
            host: 'localhost',
            port: 6379,
            retryDelayOnFailover: 100,
            lazyConnect: true
        };
    }
    
    // Check for production Redis URL (Heroku/cloud)
    if (process.env.REDISCLOUD_URL) {
        console.log("☁️ Using Redis from REDISCLOUD_URL");
        return process.env.REDISCLOUD_URL;
    }
    
    // Check for local Redis URL format  
    if (process.env.REDIS_URL) {
        console.log("🔗 Using Redis from REDIS_URL");
        return process.env.REDIS_URL;
    }
    
    // Check for individual Redis environment variables
    if (process.env.REDIS_HOST || process.env.REDIS_PORT) {
        console.log("🔧 Using Redis from REDIS_HOST/PORT");
        return {
            host: process.env.REDIS_HOST || 'localhost',
            port: parseInt(process.env.REDIS_PORT || '6379'),
            retryDelayOnFailover: 100,
            lazyConnect: true
        };
    }
    
    // Default fallback to local Redis for development
    console.log("🏠 Defaulting to local Redis (localhost:6379)");
    return {
        host: 'localhost',
        port: 6379,
        retryDelayOnFailover: 100,
        lazyConnect: true
    };
}
```

## Environment Variable Setup

### Local Development
Set one of these:
```bash
# Option 1: Explicit local development
export NODE_ENV=development

# Option 2: Force local Redis
export USE_LOCAL_REDIS=true

# Option 3: Individual Redis settings
export REDIS_HOST=localhost
export REDIS_PORT=6379
```

### Production (Heroku)
Heroku should automatically set:
```bash
REDISCLOUD_URL=redis://:password@host:port
```

## Testing Your Puppeteer Worker

### 1. Check Environment Variables
```javascript
console.log("🔧 Puppeteer Redis Environment:");
console.log("NODE_ENV:", process.env.NODE_ENV);
console.log("USE_LOCAL_REDIS:", process.env.USE_LOCAL_REDIS);
console.log("REDISCLOUD_URL:", process.env.REDISCLOUD_URL ? "SET" : "NOT SET");
console.log("REDIS_HOST:", process.env.REDIS_HOST);
console.log("REDIS_PORT:", process.env.REDIS_PORT);
```

### 2. Test Redis Connection
```javascript
const redisConfig = getRedisConfig();
console.log("🔧 Puppeteer using Redis config:", redisConfig);

const redis = new Redis(redisConfig);
redis.ping().then(() => {
    console.log("✅ Puppeteer Redis connection successful");
}).catch((error) => {
    console.error("❌ Puppeteer Redis connection failed:", error);
});
```

### 3. Test Message Reception
Your worker should see messages like this:
```json
{
    "taskType": "amazon_search",
    "searchTerm": "TEST_REDIS_CONFIG", 
    "searchType": "general",
    "taskId": "0d5e7f46-f6cd-4303-a1f6-49d726cb40c1",
    "callbackUrl": "http://localhost:8000/api/affiliate-search-callback/"
}
```

## Quick Fix Steps

1. **Update your Puppeteer worker** to use the `getRedisConfig()` function above
2. **Set environment variable** for local development:
   ```bash
   export NODE_ENV=development
   ```
3. **Restart your Puppeteer worker**
4. **Test the search** again from your Chrome extension

## Current Django Test Results

✅ **Local Development (Current)**:
- Host: localhost
- Port: 6379  
- Password: NOT SET
- Connection: SUCCESS
- Pub/Sub: 2 subscribers notified
- Search Tasks: Generated successfully

The issue is that your Puppeteer worker is likely connecting to a different Redis instance than Django. Once you update the worker to use the same Redis configuration logic, it should work perfectly! 