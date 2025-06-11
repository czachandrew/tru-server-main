#!/usr/bin/env python3

import os
import sys
import django
import json

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_platform.settings')

# Mock required environment variables
os.environ.setdefault('GOOGLE_OAUTH2_CLIENT_ID', 'dummy')
os.environ.setdefault('GOOGLE_OAUTH2_CLIENT_SECRET', 'dummy')

django.setup()

# Now import and test the search functionality
if __name__ == "__main__":
    from affiliates.tasks import generate_affiliate_url_from_search
    import redis
    import time
    from ecommerce_platform.schema import get_redis_connection
    
    print("🔍 TESTING AMAZON SEARCH FUNCTIONALITY")
    print("=" * 50)
    
    # Test cases
    test_cases = [
        {
            "name": "MacBook Pro Part Number",
            "search_term": "MX2Y3LL/A",
            "search_type": "part_number"
        },
        {
            "name": "Dell Latitude Product Name", 
            "search_term": "Dell Latitude 5550",
            "search_type": "product_name"
        },
        {
            "name": "Generic Laptop Search",
            "search_term": "laptop computer",
            "search_type": "general"
        }
    ]
    
    # Connect to Redis to monitor results
    redis_kwargs = get_redis_connection()
    r = redis.Redis(**redis_kwargs)
    
    print(f"📡 Connected to Redis: {redis_kwargs['host']}:{redis_kwargs['port']}")
    
    for test_case in test_cases:
        print(f"\n🎯 Testing: {test_case['name']}")
        print(f"   Search Term: '{test_case['search_term']}'")
        print(f"   Search Type: {test_case['search_type']}")
        
        # Generate the search task
        task_id, success = generate_affiliate_url_from_search(
            search_term=test_case['search_term'],
            search_type=test_case['search_type']
        )
        
        if success:
            print(f"   ✅ Task queued successfully: {task_id}")
            
            # Check if the message was sent to Redis
            pending_task = r.get(f"pending_search_task:{task_id}")
            if pending_task:
                task_data = json.loads(pending_task)
                print(f"   📋 Task stored in Redis: {task_data}")
            else:
                print(f"   ⚠️ Task not found in Redis")
                
            print(f"   ⏳ Task is now waiting for Puppeteer worker to process...")
            print(f"   💡 To check status manually, monitor Redis key: search_result:{task_id}")
            
        else:
            print(f"   ❌ Failed to queue task")
    
    print(f"\n📊 SUMMARY")
    print(f"   • {len(test_cases)} test cases queued")
    print(f"   • Messages sent to Redis channel: 'affiliate_tasks'")
    print(f"   • Expected message format:")
    
    example_message = {
        "taskType": "amazon_search",
        "searchTerm": "example search",
        "searchType": "part_number", 
        "taskId": "uuid-string",
        "callbackUrl": "http://localhost:8000/api/affiliate-search-callback/"
    }
    print(f"     {json.dumps(example_message, indent=6)}")
    
    print(f"\n🔧 PUPPETEER WORKER SETUP")
    print(f"   1. The Puppeteer worker should be listening to Redis channel 'affiliate_tasks'")
    print(f"   2. It should handle messages with taskType: 'amazon_search'")
    print(f"   3. Results should be sent to the callbackUrl or stored in Redis")
    print(f"   4. See PUPPETEER_SEARCH_IMPLEMENTATION_PROMPT.md for full implementation details")
    
    print(f"\n✅ TEST COMPLETE")
    print(f"   Note: These are just queue tests. Actual search results depend on Puppeteer worker.") 