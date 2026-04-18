# 🚀 DEPLOYMENT GUIDE
## ВеzemЦыплят - Production Deployment Instructions

---

## ⚡ Quick Start (5 Minutes)

### Step 1: Install Production Adapter
```bash
npm install -D @astrojs/netlify
# OR for Vercel:
# npm install -D @astrojs/vercel
```

### Step 2: Update astro.config.mjs
```javascript
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';
import netlify from '@astrojs/netlify';  // Add this

export default defineConfig({
  integrations: [react(), tailwind()],
  output: 'server',
  adapter: netlify(),  // Add this
});
```

### Step 3: Deploy
```bash
# For Netlify (recommended)
netlify deploy --prod

# OR Push to GitHub (Netlify auto-deploy)
git push origin main
```

### Step 4: Set Environment Variable
In Netlify/Vercel Dashboard:
```
BITRIX24_WEBHOOK = https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add
```

✅ **Done!** Site is now live.

---

## 📋 Pre-Deployment Checklist

### Code Quality ✅
- [x] All features tested locally
- [x] No console errors
- [x] Environment variables configured
- [x] API integration working (5+ test orders)
- [x] Responsive design verified

### SEO & Meta ✅
- [x] Meta tags added to Layout.astro
- [x] JSON-LD schemas implemented
- [x] robots.txt created
- [x] sitemap.xml created
- [x] _headers file configured
- [x] Canonical URL set

### Production Ready ✅
- [x] No hardcoded API keys
- [x] Error handling implemented
- [x] Logging set to production level
- [x] Cache headers configured
- [x] 404 and error pages work

---

## 🔧 Detailed Setup for Different Platforms

### 📍 Option A: Netlify (Recommended)

#### Via GitHub (Auto-Deploy)
1. Push project to GitHub repository
2. Connect repository to Netlify:
   - Go to https://app.netlify.com/
   - Click "New site from Git"
   - Select GitHub repository
   - Choose branch: `main`
3. Build settings:
   - **Build command:** `npm run build`
   - **Publish directory:** `dist`
4. Add environment variable:
   - Go to Site Settings → Environment
   - Add `BITRIX24_WEBHOOK` with full webhook URL

#### Via Netlify CLI
```bash
# Install Netlify CLI
npm install -g netlify-cli

# Login to Netlify
netlify login

# Create new site
netlify init
# Select: Create & configure a new site
# Choose team and site name

# Deploy
netlify deploy --prod
```

#### Via Drag & Drop
1. Build locally: `npm run build`
2. Zip `dist` folder
3. Drag into Netlify: https://app.netlify.com/drop

### 📍 Option B: Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel

# Or connect GitHub:
# https://vercel.com/new
# Select GitHub repository → Import
```

In Vercel Dashboard:
- Settings → Environment Variables
- Add `BITRIX24_WEBHOOK`

### 📍 Option C: Static Hosting (GitHub Pages)

**Not recommended for this project** (requires server-side rendering)

---

## ✅ Post-Deployment Verification

### 1. Site Accessibility
```bash
# Check site is accessible
curl https://yourdomain.com/

# Check API endpoint
curl https://yourdomain.com/api/submit-order

# Should return 405 Method Not Allowed (GET not supported)
```

### 2. SEO Files
```bash
# Verify robots.txt
https://yourdomain.com/robots.txt

# Verify sitemap.xml
https://yourdomain.com/sitemap.xml

# Verify _headers (Netlify only)
# Check via browser DevTools → Network → Response Headers
```

### 3. Submit to Search Engines

#### Google Search Console
1. Go to https://search.google.com/search-console
2. Add property: `https://yourdomain.com/`
3. Submit sitemap: `https://yourdomain.com/sitemap.xml`
4. Request indexing of homepage

#### Yandex Webmaster (for Russian audience)
1. Go to https://webmaster.yandex.ru/
2. Add site: `https://yourdomain.com/`
3. Verify ownership (DNS or file upload)
4. Submit sitemap: `https://yourdomain.com/sitemap.xml`

### 4. Test Shopping Cart
1. Navigate to https://yourdomain.com/
2. Add items to cart
3. Fill order form and submit
4. Verify order appears in Bitrix24

### 5. Test SEO Meta Tags
In browser DevTools:
```html
<!-- Should see meta tags -->
<meta name="description" content="...">
<meta property="og:title" content="...">
<meta property="og:image" content="...">

<!-- Should see JSON-LD schemas -->
<script type="application/ld+json">
  {"@context":"https://schema.org","@type":"LocalBusiness"...}
</script>
```

### 6. Performance Check
- Google PageSpeed Insights: https://pagespeed.web.dev/
- Check Core Web Vitals (LCP, CLS, FID)
- Monitor first 24 hours of traffic

---

## 🐛 Troubleshooting

### Issue: "Adapter is not installed"
**Solution:**
```bash
npm install -D @astrojs/netlify
# Update astro.config.mjs with: adapter: netlify()
```

### Issue: API returns 404
**Cause:** Adapter not installed or build failed  
**Solution:** Check build logs in Netlify/Vercel dashboard

### Issue: BITRIX24_WEBHOOK is undefined
**Cause:** Environment variable not set  
**Solution:** Add to dashboard:
```
BITRIX24_WEBHOOK=https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add
```

### Issue: Cart not persisting
**Cause:** localStorage not working (shouldn't happen in production)  
**Solution:** Check browser console for errors

### Issue: Orders not appearing in Bitrix24
**Cause:** Webhook URL is wrong or Bitrix24 API changed  
**Solution:** 
1. Check webhook URL in .env
2. Test webhook manually:
```bash
curl -X POST https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add \
  -H "Content-Type: application/json" \
  -d '{"fields":{"TITLE":"Test","NAME":"Test User"}}'
```

### Issue: Sitemap returns 404
**Cause:** File not deployed to `public/` folder  
**Solution:** Ensure `public/sitemap.xml` exists and was built

---

## 📊 Monitoring & Maintenance

### Daily Checks
- [ ] Website loads successfully
- [ ] Cart adds items correctly
- [ ] Order form submits without errors
- [ ] New orders appear in Bitrix24

### Weekly Checks
- [ ] Monitor Google PageSpeed Insights scores
- [ ] Check Netlify/Vercel analytics
- [ ] Review error logs in deployment dashboard
- [ ] Verify no console errors (DevTools)

### Monthly Checks
- [ ] Review search engine performance (Google Search Console)
- [ ] Check Yandex analytics (for Russian audience)
- [ ] Monitor Bitrix24 order creation rate
- [ ] Review Core Web Vitals metrics

### Quarterly Reviews
- [ ] Analyze user behavior (Google Analytics)
- [ ] Update SEO content based on search trends
- [ ] Optimize images for better performance
- [ ] Review and update product catalog

---

## 🔒 Security Considerations

### API Key Protection
✅ BITRIX24_WEBHOOK is only in environment variables (not in code)
✅ API route has proper error handling
✅ No sensitive data logged to console

### CORS & Headers
✅ _headers file configured for proper cache control
✅ _redirects file configured for URL rewriting

### Rate Limiting
⚠️ **TODO:** Consider adding rate limiting to API endpoint
```javascript
// Example: Limit to 10 requests per minute
const rateLimit = {};
```

### Input Validation
✅ Order form validates required fields
✅ API validates JSON structure
✅ Phone number format checked

---

## 📈 Performance Optimization Tips

### Already Implemented ✅
- [x] Tailwind CSS (optimized)
- [x] Asset minification (Astro handles)
- [x] Cache headers configured
- [x] sitemap.xml for indexing

### Future Improvements 🔄
- [ ] Image optimization (WebP, lazy loading)
- [ ] Component code splitting
- [ ] Static site generation for non-API routes
- [ ] CDN setup for assets
- [ ] Database for product catalog

---

## 💬 Getting Help

### Check These Files
1. `PROJECT_STATUS.md` - Complete project overview
2. `SEO_OPTIMIZATION.md` - SEO implementation details
3. `FEATURES.md` - Feature documentation
4. `CATALOG_GUIDE.md` - Product catalog info

### Check These Logs
- Netlify/Vercel deployment logs
- Browser console (DevTools)
- Network tab (for API calls)
- Bitrix24 CRM logs

### Common Commands
```bash
# Local development
npm run dev

# Build for production
npm run build

# Preview production build locally
npm run preview

# Check for errors
npm run build -- --verbose

# Clear cache
rm -rf node_modules/.astro
npm run build
```

---

## 🎉 Deployment Checklist - Final

Before going live:
- [ ] Adapter installed and configured
- [ ] Environment variables set in dashboard
- [ ] Local build succeeds: `npm run build`
- [ ] Local preview works: `npm run preview`
- [ ] No console errors or warnings
- [ ] robots.txt is accessible
- [ ] sitemap.xml is accessible
- [ ] API endpoint responds correctly
- [ ] Cart functionality works
- [ ] Order form submits successfully
- [ ] Orders appear in Bitrix24

After going live:
- [ ] Test all features on production URL
- [ ] Submit sitemap to Google Search Console
- [ ] Submit sitemap to Yandex Webmaster
- [ ] Monitor first 24 hours for errors
- [ ] Check PageSpeed Insights
- [ ] Monitor order flow

---

**Ready to deploy?** Let's go! 🚀

For questions or issues, refer to `PROJECT_STATUS.md` for detailed troubleshooting.

Last updated: October 21, 2025
