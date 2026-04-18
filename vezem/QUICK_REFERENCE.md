# 🎯 QUICK REFERENCE GUIDE
## ВеzemЦыплят - Common Tasks & Solutions

---

## ⚡ Quick Commands

```bash
# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Install dependencies
npm install
```

---

## 🛒 Cart Functions

```javascript
// Add item to cart (shows green Toast)
window.addToCart('ross308', 'РОСС-308', 85, 10, false)

// Refresh cart UI (reads from localStorage)
window.updateCartUI()

// Change quantity of existing item
window.updateQuantity('ross308', 20)

// Remove item from cart
window.removeFromCart('ross308')

// Open order form modal (validates cart first)
window.openOrderModal()

// Close order form
window.closeOrderModal()
```

---

## 🔔 Notification Functions

```javascript
// Success notification (green, auto-closes in 4s)
window.showToast('✅ Item added!', 'success')

// Error notification (red)
window.showToast('❌ Error occurred', 'error')

// Info notification (blue)
window.showToast('ℹ️ Information', 'info')

// Warning notification (yellow)
window.showToast('⚠️ Warning!', 'warning')

// Custom duration (in milliseconds)
window.showToast('Message', 'success', 6000)  // 6 seconds
```

---

## 📝 Common File Locations

| Task | File | Line |
|------|------|------|
| Edit products | `src/components/Products.astro` | - |
| Edit cart | `src/components/FloatingCart.astro` | - |
| Edit order form | `src/components/OrderForm.astro` | - |
| Edit API | `src/pages/api/submit-order.ts` | - |
| Edit styling | `src/styles/global.css` | - |
| Edit meta tags | `src/layouts/Layout.astro` | `<head>` |
| Edit robots.txt | `public/robots.txt` | - |
| Edit sitemap | `public/sitemap.xml` | - |

---

## 🔧 Editing Tasks

### Add New Product
**File:** `src/components/Products.astro`

```javascript
{
  id: 'new-product',
  name: 'Product Name',
  price: 100,  // 0 for quote
  category: 'chickens',
  description: 'Brief description',
  image: '/Hero.png',
  requiresQuote: false
}
```

### Update Meta Tags
**File:** `src/layouts/Layout.astro`

```html
<meta name="description" content="New description">
<meta property="og:title" content="New Title">
```

### Change Webhook URL
**File:** `.env`

```
BITRIX24_WEBHOOK=https://new-webhook-url.com/crm.lead.add
```

### Customize Colors
**File:** `src/styles/global.css`

Update Tailwind color classes (e.g., `bg-gradient-to-r from-emerald-500 to-green-600`)

---

## 🐛 Troubleshooting Quick Fixes

### Cart Not Working
```javascript
// Clear and reload
localStorage.clear()
location.reload()
```

### Orders Not Submitted
1. Check `.env` file has BITRIX24_WEBHOOK
2. Verify webhook URL is correct
3. Check browser console (F12) for errors
4. Test manually: `window.openOrderModal()`

### Form Validation Failing
1. Check all required fields (name, phone, address)
2. Verify cart has items: `localStorage.getItem('cart')`
3. Check browser console for details

### Notifications Not Showing
```javascript
// Test notification system
window.showToast('Test message', 'success')
```

### Build Failing
```bash
# Clear cache and rebuild
rm -rf node_modules/.astro
npm run build
```

---

## 📊 Checking System Status

### Is Server Running?
```bash
# Should show: Local http://localhost:4321/
npm run dev
```

### Check API Endpoint
```bash
# In browser console:
fetch('/api/submit-order', {method: 'POST', body: JSON.stringify({})})
  .then(r => r.json()).then(console.log)
```

### View Cart Data
```javascript
// In browser console:
console.log(JSON.parse(localStorage.getItem('cart')))
```

### Check for Errors
```javascript
// Look in browser console (F12 > Console tab)
// Production code should have no errors
```

---

## 🔗 API Endpoint Details

**URL:** `/api/submit-order`  
**Method:** POST  
**Content-Type:** application/json  

**Request:**
```json
{
  "orderInfo": {
    "name": "Name",
    "phone": "+7999999999",
    "address": "Address",
    "comment": "Comment",
    "items": [...]
  }
}
```

**Success Response:** 200 OK
```json
{
  "success": true,
  "leadId": 11,
  "totalSum": 850
}
```

**Error Response:** 400/500
```json
{
  "error": "Error message",
  "details": "..."
}
```

---

## 📁 Project Structure Quick Reference

```
src/pages/api/           ← API endpoints
src/pages/index.astro    ← Main page
src/components/          ← UI components
  - Products.astro       ← Product catalog
  - FloatingCart.astro   ← Shopping cart
  - OrderForm.astro      ← Order form
  - Toast.astro          ← Notifications
src/layouts/Layout.astro ← Meta tags & SEO
src/styles/global.css    ← Styling
public/                  ← Static files
  - robots.txt           ← SEO robots
  - sitemap.xml          ← SEO sitemap
```

---

## 🌐 Environment Variables

### Required in `.env`
```
BITRIX24_WEBHOOK=https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add
```

### For Deployment
Set in Netlify/Vercel dashboard:
- BITRIX24_WEBHOOK (same as above)

---

## ✅ Pre-Deployment Checklist

- [ ] `npm run build` succeeds
- [ ] No console errors
- [ ] Test order submits to Bitrix24
- [ ] Responsive design works (test on phone)
- [ ] Meta tags present (F12 > Elements > head)
- [ ] robots.txt accessible
- [ ] sitemap.xml accessible
- [ ] Adapter installed: `@astrojs/netlify` or `@astrojs/vercel`
- [ ] astro.config.mjs has adapter configured
- [ ] Environment variable set in deployment dashboard

---

## 📖 Documentation Files

| File | Purpose | When to Read |
|------|---------|--------------|
| README.md | Project overview | First thing |
| QUICK_REFERENCE.md | This file | Constant lookup |
| COMPLETION_SUMMARY.md | What was built | Project summary |
| PROJECT_STATUS.md | Detailed report | Deep dive |
| DEPLOYMENT_GUIDE.md | How to deploy | Before going live |
| SEO_OPTIMIZATION.md | SEO details | SEO questions |

---

## 🎯 Most Common Tasks

### Task 1: Add Product
1. Open `src/components/Products.astro`
2. Find `const products = [` array
3. Add new object with product details
4. Restart dev server
5. Test on http://localhost:4321/

### Task 2: Fix Order Not Submitting
1. Check `.env` file exists
2. Verify BITRIX24_WEBHOOK URL correct
3. Open browser console (F12)
4. Test order submission
5. Check for error messages

### Task 3: Update SEO Tags
1. Open `src/layouts/Layout.astro`
2. Find `<head>` section
3. Update meta tags
4. Save and check in browser (F12 > Elements)

### Task 4: Change Styling
1. Open `src/styles/global.css`
2. Update Tailwind classes
3. Auto-reloads in dev mode
4. Test responsive (F12 > Toggle device toolbar)

### Task 5: Deploy to Production
1. Install adapter: `npm install -D @astrojs/netlify`
2. Update astro.config.mjs with adapter
3. Connect to GitHub (Netlify auto-deploy)
4. Set BITRIX24_WEBHOOK environment variable
5. Deploy: `netlify deploy --prod`

---

## 💡 Pro Tips

### Debug Order Issues
```javascript
// Check if order was sent
localStorage.getItem('cart')

// Manually create order
window.openOrderModal()

// Check form validation
document.querySelector('#order-form').checkValidity()
```

### Monitor API Calls
```javascript
// In browser DevTools:
// 1. Open Network tab (F12 > Network)
// 2. Add item to cart
// 3. Submit order
// 4. Look for /api/submit-order POST request
// 5. Click on it to see request/response
```

### Check Responsive Design
```javascript
// In browser:
// 1. Press F12 to open DevTools
// 2. Click toggle device toolbar (top-left)
// 3. Select different devices to test
// 4. Check all elements work on mobile
```

### Test SEO Meta Tags
```javascript
// In browser console:
document.querySelector('meta[name="description"]').content
document.querySelector('meta[property="og:title"]').content
```

---

## 🚀 Quick Deploy Steps

```bash
# 1. Install adapter (1 minute)
npm install -D @astrojs/netlify

# 2. Build locally to test (2 minutes)
npm run build

# 3. If build succeeds, deploy
netlify deploy --prod

# 4. Set environment variable in Netlify dashboard
# BITRIX24_WEBHOOK=https://...

# 5. Test on production URL
# - Add to cart
# - Submit order
# - Check Bitrix24
```

---

## 📞 Error Messages & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `POST /api/submit-order 404` | Adapter not installed | Install @astrojs/netlify |
| `Webhook not configured` | BITRIX24_WEBHOOK not set | Add to .env or dashboard |
| `Cannot parse JSON` | Malformed request body | Check order form data |
| `Cart is empty` | No items added | Add products to cart |
| `Form validation error` | Missing required field | Fill name, phone, address |
| `Orders not in Bitrix24` | API call failed | Check webhook URL |
| `Cart not persisting` | localStorage issue | Clear: `localStorage.clear()` |
| `Notifications not showing` | Toast not included | Toast.astro is in Layout.astro |

---

## 🎓 Key Concepts

### Cart Structure
```javascript
// Items with fixed price
regular: [
  { id, name, price, quantity, requiresQuote: false }
]

// Items needing price quote
needsQuote: [
  { id, name, price: 0, quantity, requiresQuote: true }
]
```

### Bitrix24 Lead
- **TITLE:** Order summary (e.g., "Заказ от 123 - 850 ₽")
- **NAME:** Customer name
- **PHONE:** Contact phone
- **ADDRESS:** Delivery address
- **OPPORTUNITY:** Total order sum
- **COMMENTS:** Full order details
- **PRODUCT ROWS:** Individual items with quantities

### Toast Types
- `success` (green) - Order added, submission successful
- `error` (red) - Validation failed, API error
- `info` (blue) - General information
- `warning` (yellow) - Missing fields, low stock

---

## ✨ Feature Overview

**Shopping Cart:**
- Add/remove items
- Update quantities
- localStorage persistence
- Real-time UI sync
- Auto clear on order success

**Order Form:**
- Name, phone, address fields
- Optional comment
- Auto-populated products
- Full validation
- Success confirmation

**Bitrix24 Integration:**
- LEAD creation
- Product rows added
- Order details captured
- Phone/address stored

**Notifications:**
- Toast system (4 types)
- Auto-close (4 seconds)
- Manual close button
- Animations
- No system alerts

**SEO:**
- 15+ meta tags
- 3 JSON-LD schemas
- robots.txt
- sitemap.xml
- Cache headers

---

**Last Updated:** October 21, 2025  
**Use this guide for:** Quick lookups, common tasks, troubleshooting

**Need detailed info?** Check the full documentation files listed above.
