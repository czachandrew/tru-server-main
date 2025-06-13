#!/usr/bin/env python3
import redis
import json
from urllib.parse import urlparse

# Use Heroku Redis URL
redis_url = "redis://default:g1dsAfatPjZ6FFU8v1B1EVGCiXYOX2Pk@redis-18551.c10.us-east-1-2.ec2.redns.redis-cloud.com:18551"

url = urlparse(redis_url)
redis_kwargs = {
    'host': url.hostname,
    'port': url.port,
    'password': url.password,
    'decode_responses': True
}

r = redis.Redis(**redis_kwargs)
pubsub = r.pubsub()
pubsub.subscribe('affiliate_tasks')

print("🔍 Monitoring affiliate_tasks channel...")
print("Now test your Chrome extension on an Amazon page!")

try:
    for message in pubsub.listen():
        if message['type'] == 'message':
            print(f"📨 TASK RECEIVED: {message['data']}")
            try:
                data = json.loads(message['data'])
                print(f"   🔗 ASIN: {data.get('asin', 'unknown')}")
                print(f"   🆔 Task ID: {data.get('taskId', 'unknown')}")
                print(f"   📞 Callback: {data.get('callbackUrl', 'unknown')}")
            except:
                pass
except KeyboardInterrupt:
    print("\n✅ Monitor stopped") 