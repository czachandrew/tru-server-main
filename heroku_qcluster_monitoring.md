# 🔍 Monitoring Django-Q Cluster on Heroku Production

## **1. Real-Time Log Tailing**

### **General App Logs:**
```bash
# Tail all logs from your Heroku app
heroku logs --tail --app YOUR-APP-NAME

# Tail only last 100 lines first, then stream
heroku logs --tail --num 100 --app YOUR-APP-NAME
```

### **Worker-Specific Logs:**
```bash
# If you have dedicated worker dynos
heroku logs --tail --dyno=worker --app YOUR-APP-NAME

# If Q-Cluster runs in web dyno
heroku logs --tail --dyno=web --app YOUR-APP-NAME

# Filter for Django-Q specific logs
heroku logs --tail --app YOUR-APP-NAME | grep -i "q_cluster\|django_q\|qcluster"
```

### **Filter for Affiliate Task Logs:**
```bash
# Monitor affiliate-specific activity
heroku logs --tail --app YOUR-APP-NAME | grep -i "affiliate\|redis\|task"
```

## **2. Check Running Processes**

### **See What's Running:**
```bash
# List all dynos and their status
heroku ps --app YOUR-APP-NAME

# Scale info
heroku ps:scale --app YOUR-APP-NAME
```

### **Expected Output:**
```
=== web (Free): gunicorn ecommerce_platform.wsgi
web.1: up 2023/01/15 14:30:00 +0000 (~ 2h ago)

=== worker (Free): python manage.py qcluster  
worker.1: up 2023/01/15 14:30:00 +0000 (~ 2h ago)
```

## **3. Django-Q Specific Monitoring Commands**

### **Run Django Shell on Heroku:**
```bash
# Access Django shell on production
heroku run python manage.py shell --app YOUR-APP-NAME
```

### **In Django Shell - Check Q-Cluster Status:**
```python
# Check Django-Q broker connection
from django_q.brokers import get_broker
broker = get_broker()
print(f"Broker: {broker}")
print(f"Connection: {broker.connection}")

# Check recent tasks
from django_q.models import Task
recent_tasks = Task.objects.order_by('-stopped')[:10]
for task in recent_tasks:
    print(f"Task: {task.func} | Success: {task.success} | Started: {task.started}")

# Check failed tasks
failed_tasks = Task.objects.filter(success=False).order_by('-stopped')[:5]
for task in failed_tasks:
    print(f"FAILED: {task.func} | Error: {task.result}")

# Check schedule
from django_q.models import Schedule
schedules = Schedule.objects.all()
for schedule in schedules:
    print(f"Scheduled: {schedule.func} | Next: {schedule.next_run}")
```

### **Check Redis Connection:**
```python
# Test Redis connectivity  
import redis
import os
from urllib.parse import urlparse

redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL')
if redis_url:
    url = urlparse(redis_url)
    r = redis.Redis(
        host=url.hostname,
        port=url.port, 
        password=url.password,
        decode_responses=True
    )
    
    # Test connection
    try:
        r.ping()
        print("✅ Redis connection successful")
        
        # Check pending affiliate tasks
        pending_keys = r.keys("pending_*")
        print(f"📋 Pending tasks: {len(pending_keys)}")
        
        for key in pending_keys[:5]:  # Show first 5
            value = r.get(key)
            print(f"   {key}: {value}")
            
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
```

## **4. Environment Variable Checks**

### **Check Configuration:**
```bash
# Check all environment variables
heroku config --app YOUR-APP-NAME

# Check specific Django-Q related vars
heroku config:get REDIS_URL --app YOUR-APP-NAME
heroku config:get REDISCLOUD_URL --app YOUR-APP-NAME
heroku config:get BASE_URL --app YOUR-APP-NAME
heroku config:get DJANGO_SETTINGS_MODULE --app YOUR-APP-NAME
```

### **Fix Missing BASE_URL (Critical!):**
```bash
# Set correct production URL for callbacks
heroku config:set BASE_URL=https://YOUR-APP-NAME.herokuapp.com --app YOUR-APP-NAME
```

## **5. Debug Affiliate Tasks Specifically**

### **Create Debug Script on Heroku:**
```bash
# Run affiliate debug command
heroku run python manage.py shell -c "
from affiliates.tasks import debug_affiliate_links
debug_affiliate_links()
" --app YOUR-APP-NAME
```

### **Check Affiliate Link Status:**
```bash
heroku run python manage.py shell -c "
from affiliates.models import AffiliateLink
links = AffiliateLink.objects.all()[:10]
for link in links:
    status = 'COMPLETE' if link.affiliate_url else 'PENDING'
    print(f'ID: {link.id} | ASIN: {link.platform_id} | Status: {status}')
" --app YOUR-APP-NAME
```

## **6. Q-Cluster Management Commands**

### **Restart Q-Cluster:**
```bash
# Restart worker dyno (if dedicated)
heroku ps:restart worker --app YOUR-APP-NAME

# Or restart entire app
heroku ps:restart --app YOUR-APP-NAME
```

### **Scale Q-Cluster:**
```bash
# Scale up worker dynos
heroku ps:scale worker=1 --app YOUR-APP-NAME

# Scale down (stop Q-Cluster)
heroku ps:scale worker=0 --app YOUR-APP-NAME
```

## **7. Common Issues & Solutions**

### **Issue: No Worker Dyno Running**
```bash
# Check if worker is defined in Procfile
heroku run cat Procfile --app YOUR-APP-NAME

# Expected: 
# web: gunicorn ecommerce_platform.wsgi
# worker: python manage.py qcluster
```

### **Issue: Redis Connection Fails**
```bash
# Check Redis addon
heroku addons --app YOUR-APP-NAME

# Should show RedisCloud or similar
# If missing, add Redis:
heroku addons:create rediscloud:30 --app YOUR-APP-NAME
```

### **Issue: Callback URLs Wrong**
```bash
# Fix BASE_URL for production callbacks
heroku config:set BASE_URL=https://YOUR-APP-NAME.herokuapp.com --app YOUR-APP-NAME

# Restart after setting
heroku ps:restart --app YOUR-APP-NAME
```

## **8. Real-Time Monitoring Setup**

### **Option A: Multiple Terminal Windows**
```bash
# Terminal 1: General logs
heroku logs --tail --app YOUR-APP-NAME

# Terminal 2: Worker-specific
heroku logs --tail --dyno=worker --app YOUR-APP-NAME  

# Terminal 3: Filter for affiliate tasks
heroku logs --tail --app YOUR-APP-NAME | grep "affiliate\|task\|redis"
```

### **Option B: Heroku Dashboard**
- Go to https://dashboard.heroku.com/apps/YOUR-APP-NAME
- Click "More" → "View logs"
- Monitor in real-time through web interface

## **🚀 Quick Troubleshooting Checklist**

1. **✅ Check worker dyno is running:** `heroku ps --app YOUR-APP-NAME`
2. **✅ Verify Redis connection:** Check config vars and test in shell
3. **✅ Fix BASE_URL:** Set production URL for callbacks  
4. **✅ Monitor logs:** `heroku logs --tail --app YOUR-APP-NAME`
5. **✅ Test affiliate task:** Create new task and watch logs
6. **✅ Check task status:** Use Django shell to inspect Task model

## **📱 Pro Tips**

- **Use `grep`** to filter logs for specific components
- **Keep logs running** in background while testing affiliate links
- **Check both web and worker dynos** if you have separate processes
- **Monitor Redis keys** to see if tasks are being queued properly
- **Watch for callback URL errors** in Puppeteer worker responses 