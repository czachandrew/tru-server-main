# Heroku Q Cluster Monitoring Guide

## ✅ Current Status: RUNNING
- **App**: `tru-prime`
- **Worker Dyno**: `worker.1` running `python manage.py qcluster`
- **Status**: Active and processing tasks

## 🔍 **Quick Health Checks**

### 1. Check Dyno Status
```bash
heroku ps -a tru-prime
```
**Expected Output:**
```
=== worker (Eco): python manage.py qcluster (1)
worker.1: up 2025/08/12 22:53:15 -0500 (~ 20m ago)
```

### 2. Check Recent Q Cluster Logs
```bash
heroku logs -a tru-prime --dyno=worker.1 --tail
```
**Look for:**
- `[Q] INFO Process-X processing [task-name]`
- `[Q] INFO Processed [task-name]`
- No error messages or exceptions

### 3. Check Task Queue via Django Admin
1. Go to your Heroku app URL + `/admin/`
2. Navigate to "Django Q" section
3. Check "Tasks" and "Schedules"

## 🚨 **Troubleshooting Commands**

### If Q Cluster is Down
```bash
# Restart the worker dyno
heroku ps:restart worker.1 -a tru-prime

# Scale worker dyno (ensure it's running)
heroku ps:scale worker=1 -a tru-prime
```

### If Tasks are Stuck
```bash
# Check for failed tasks in Django admin
# Or use Django shell:
heroku run python manage.py shell -a tru-prime
```

### Check Redis Connection (Q Cluster uses Redis)
```bash
# Check Redis addon status
heroku addons -a tru-prime

# Check Redis connection logs
heroku logs -a tru-prime --source=heroku-redis
```

## 📊 **Monitoring Scripts**

### Quick Status Script
```bash
#!/bin/bash
echo "=== Heroku Q Cluster Status ==="
echo "Dyno Status:"
heroku ps -a tru-prime | grep worker
echo ""
echo "Recent Activity:"
heroku logs -a tru-prime --dyno=worker.1 --num=5
```

### Health Check URL
If you want to create a health check endpoint, add this to your Django views:
```python
# In views.py
from django.http import JsonResponse
from django_q.models import Task
from datetime import datetime, timedelta

def qcluster_health(request):
    # Check recent task activity
    recent_tasks = Task.objects.filter(
        stopped__gte=datetime.now() - timedelta(minutes=10)
    ).count()
    
    return JsonResponse({
        'status': 'healthy' if recent_tasks > 0 else 'inactive',
        'recent_tasks': recent_tasks,
        'timestamp': datetime.now().isoformat()
    })
```

## 🔧 **Common Issues & Solutions**

### Issue: Worker Dyno Sleeping (Eco Tier)
**Solution:** Upgrade to Basic tier or use a service like "Heroku Scheduler" to ping your worker regularly.

### Issue: Redis Connection Lost
**Solution:** 
```bash
heroku addons:info redis -a tru-prime
heroku config -a tru-prime | grep REDIS
```

### Issue: High Memory Usage
**Solution:**
```bash
# Check memory usage
heroku logs -a tru-prime --dyno=worker.1 | grep "Error R14"

# Restart if needed
heroku ps:restart worker.1 -a tru-prime
```

## 📱 **Mobile Monitoring**

Install Heroku mobile app for quick checks:
- iOS: https://apps.apple.com/app/heroku/id1127564285
- Android: https://play.google.com/store/apps/details?id=com.heroku.android

## 🎯 **Key Metrics to Watch**

1. **Dyno Uptime**: Should be consistent unless you restart
2. **Task Processing**: Look for regular `[Q] INFO Processed` messages
3. **Error Rate**: Should be minimal in logs
4. **Memory Usage**: Watch for R14 errors
5. **Redis Connectivity**: Ensure Redis addon is healthy

## ⚡ **Pro Tips**

1. **Set up log drains** for better log management:
   ```bash
   heroku logs:config -a tru-prime
   ```

2. **Use papertrail addon** for better log searching:
   ```bash
   heroku addons:create papertrail -a tru-prime
   ```

3. **Monitor with New Relic** (if using):
   ```bash
   heroku addons:create newrelic -a tru-prime
   ```

---

## 🎉 **Current Status Summary**

✅ **Q Cluster is RUNNING and HEALTHY**
- Worker dyno: UP (20+ minutes)
- Processing tasks: ACTIVE
- No critical errors detected

Your affiliate tracking, purchase intent processing, and wallet transactions should be working properly!

