# Demo Products System Guide

## Overview

The demo products system allows you to quickly populate your database with realistic product data for presentations and testing. This ensures you always have that "oh shit" moment covered during demos!

## Features

- **Realistic Products**: MacBook Pro, Dell XPS, HP EliteBook, Logitech accessories, etc.
- **Flagged Data**: All demo products are marked with `is_demo=True` for easy identification
- **Easy Cleanup**: Bulk delete all demo products when ready for production
- **Multiple Interfaces**: Django admin, management commands, and API endpoints

## Quick Start

### 1. Create Demo Products

**Via Management Command:**
```bash
# Create 10 demo products
python manage.py create_demo_products --count 10

# Clear existing demo products and create new ones
python manage.py create_demo_products --clear-existing --count 15
```

**Via API:**
```bash
# Enable demo mode (creates products)
curl -X POST https://your-app.herokuapp.com/products/toggle-demo-mode/ \
  -H "Content-Type: application/json" \
  -d '{"action": "enable"}'

# Check demo status
curl https://your-app.herokuapp.com/products/demo-status/
```

### 2. Django Admin Interface

Navigate to `/admin/products/product/` and you'll see:
- **Demo Filter**: Filter by "Is demo" to see only demo products
- **Bulk Actions**: 
  - "Mark selected products as demo"
  - "Mark selected products as production" 
  - "Delete demo products only"

### 3. Clean Up Demo Data

**Via Management Command:**
```bash
python manage.py create_demo_products --clear-existing --count 0
```

**Via API:**
```bash
curl -X POST https://your-app.herokuapp.com/products/toggle-demo-mode/ \
  -H "Content-Type: application/json" \
  -d '{"action": "disable"}'
```

**Via Django Admin:**
1. Go to Products admin
2. Filter by "Is demo: Yes"
3. Select all products
4. Choose "Delete demo products only" action

## Demo Products Included

The system creates realistic products that people commonly search for:

### Laptops
- **MacBook Pro 13-inch** (Apple M2, 8GB RAM, 256GB SSD)
- **MacBook Air 13-inch** (Apple M2, 8GB RAM, 256GB SSD)
- **Dell XPS 13** (Intel Core i7, 16GB RAM, 512GB SSD)
- **Dell Latitude 7420** (Intel Core i5, 8GB RAM, 256GB SSD)
- **HP EliteBook 840** (Intel Core i5, 16GB RAM, 512GB SSD)
- **HP Pavilion 15** (AMD Ryzen 5, 8GB RAM, 256GB SSD)

### Accessories
- **Logitech MX Master 3** (Wireless mouse, 70-day battery)
- **Logitech MX Keys** (Wireless keyboard with backlight)
- **Dell Monitor 27 inch** (4K USB-C monitor)
- **Apple Magic Mouse** (Multi-touch wireless mouse)

## API Endpoints

### GET /products/demo-status/
Returns current demo product status:
```json
{
    "demo_products_count": 10,
    "total_products_count": 32900,
    "demo_enabled": true
}
```

### POST /products/toggle-demo-mode/
Enable or disable demo mode:

**Enable (create demo products):**
```json
{
    "action": "enable"
}
```

**Disable (delete demo products):**
```json
{
    "action": "disable"
}
```

## Production Deployment

### Heroku Commands

```bash
# Create demo products on Heroku
heroku run "python manage.py create_demo_products --count 10"

# Clear demo products on Heroku
heroku run "python manage.py create_demo_products --clear-existing --count 0"

# Check status
curl https://your-app.herokuapp.com/products/demo-status/
```

## Best Practices

1. **Before Demos**: Always run the demo creation command to ensure fresh, consistent data
2. **After Demos**: Clean up demo products to avoid confusion with real data
3. **Production**: Never deploy with demo products enabled
4. **Testing**: Use demo products for automated testing and development

## Database Schema

The `Product` model includes:
```python
is_demo = models.BooleanField(default=False, help_text="Mark this product as demo data for testing/presentations")
```

This allows you to:
- Filter demo vs. production products
- Bulk operations on demo data only
- Analytics excluding demo data
- Easy cleanup before going live

## Troubleshooting

**Issue**: Command fails with manufacturer conflicts
**Solution**: The command automatically handles existing manufacturers and creates new ones only if needed.

**Issue**: Demo products not appearing in search
**Solution**: Ensure your search functionality doesn't exclude `is_demo=True` products during development.

**Issue**: Can't delete demo products
**Solution**: Use the specific "Delete demo products only" admin action or the API endpoint rather than regular delete operations.

## Integration with Your Chrome Extension

The demo products are designed to trigger exact matches for common search terms:
- "MacBook Pro" → Returns Apple MacBook Pro 13-inch
- "Dell XPS" → Returns Dell XPS 13
- "Logitech mouse" → Returns Logitech MX Master 3
- "HP laptop" → Returns HP EliteBook 840 or HP Pavilion 15

This ensures your Chrome extension will always find relevant products during demos, creating that reliable "wow" moment for potential customers. 