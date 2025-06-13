#!/bin/bash

# Quick Heroku Q-Cluster Monitoring Script
# Replace YOUR-APP-NAME with your actual Heroku app name

APP_NAME="$1"

if [ -z "$APP_NAME" ]; then
    echo "🚨 Usage: ./quick_heroku_monitor.sh YOUR-APP-NAME"
    echo ""
    echo "Example: ./quick_heroku_monitor.sh my-ecommerce-app"
    exit 1
fi

echo "🔍 Starting Heroku Q-Cluster Monitoring for: $APP_NAME"
echo "================================================================"

# Check if app exists
if ! heroku apps:info --app "$APP_NAME" > /dev/null 2>&1; then
    echo "❌ Error: App '$APP_NAME' not found or no access"
    echo "💡 Try: heroku apps:list"
    exit 1
fi

echo ""
echo "📋 1. Checking running processes..."
heroku ps --app "$APP_NAME"

echo ""
echo "🔧 2. Checking critical environment variables..."
echo "BASE_URL: $(heroku config:get BASE_URL --app "$APP_NAME")"
echo "REDIS_URL: $(heroku config:get REDIS_URL --app "$APP_NAME" | cut -c1-50)..."
echo "REDISCLOUD_URL: $(heroku config:get REDISCLOUD_URL --app "$APP_NAME" | cut -c1-50)..."

echo ""
echo "⚠️  3. Critical Issue Check:"
BASE_URL=$(heroku config:get BASE_URL --app "$APP_NAME")
if [[ "$BASE_URL" == *"localhost"* ]] || [[ "$BASE_URL" == *"127.0.0.1"* ]] || [ -z "$BASE_URL" ]; then
    echo "🚨 CALLBACK URL ISSUE DETECTED!"
    echo "   Current BASE_URL: $BASE_URL"
    echo "   🔧 Fix: heroku config:set BASE_URL=https://$APP_NAME.herokuapp.com --app $APP_NAME"
    echo ""
fi

echo ""
echo "🎯 4. Starting real-time log monitoring..."
echo "   💡 Press Ctrl+C to stop"
echo "   🔍 Filtering for: qcluster, django_q, affiliate, redis, task"
echo ""

# Start tailing logs with filters
heroku logs --tail --app "$APP_NAME" | grep -i --line-buffered "qcluster\|django_q\|affiliate\|redis\|task\|worker\|error" 