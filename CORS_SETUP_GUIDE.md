# CORS Configuration Guide for Flash-AI

## What is CORS?

CORS (Cross-Origin Resource Sharing) allows your frontend to make requests to your backend from different domains/ports.

Without CORS, you'll see errors like:
```
Failed to fetch
Access to XMLHttpRequest blocked by CORS policy
URL scheme must be "http" or "https"
```

---

## Local Development

The CORS is already configured for local development with these origins:

```env
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:8000
```

This allows requests from:
- React dev server (port 3000, 5173)
- FastAPI backend (port 8000)
- 127.0.0.1 variants

---

## Production VPS Deployment

### Option 1: Single Domain (Recommended)

```env
ALLOWED_ORIGINS=https://your-domain.com
```

For subdomains:
```env
ALLOWED_ORIGINS=https://your-domain.com,https://api.your-domain.com,https://app.your-domain.com
```

### Option 2: Multiple Domains

```env
ALLOWED_ORIGINS=https://domain1.com,https://domain2.com,https://app.example.com
```

### Option 3: Allow All (NOT recommended for production!)

```env
ALLOWED_ORIGINS=*
```

Use this only for testing, never in production.

---

## How to Update CORS on VPS

### 1. SSH into VPS
```bash
ssh root@your_vps_ip
```

### 2. Navigate to project
```bash
cd /opt/Flash-AI/Flash-AI
```

### 3. Edit .env
```bash
nano .env
```

### 4. Update ALLOWED_ORIGINS
```env
# Replace with your domain
ALLOWED_ORIGINS=https://your-domain.com

# Or with multiple domains
ALLOWED_ORIGINS=https://your-domain.com,https://api.your-domain.com,https://www.your-domain.com
```

### 5. Save and exit
- Press `Ctrl + X`
- Press `Y`
- Press `Enter`

### 6. Rebuild and restart
```bash
docker-compose build --no-cache
docker-compose down
docker-compose up -d
```

### 7. Verify CORS is working
```bash
# Check logs
docker-compose logs backend | grep CORS

# Expected output:
# INFO CORS enabled for origins: https://your-domain.com
```

---

## Testing CORS

### From Browser Console
```javascript
// Test if API is accessible
fetch('http://localhost:8000/docs')
  .then(r => r.text())
  .then(d => console.log('✅ CORS working!'))
  .catch(e => console.log('❌ CORS error:', e.message))
```

### From Command Line
```bash
# Test preflight request
curl -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS http://localhost:8000/chat -v

# Should see: Access-Control-Allow-Origin: http://localhost:3000
```

---

## Common CORS Issues & Solutions

### Issue 1: "Access to XMLHttpRequest blocked by CORS policy"

**Solution:** Add your frontend URL to `ALLOWED_ORIGINS` in `.env`

```env
# If frontend is on https://app.example.com
ALLOWED_ORIGINS=https://app.example.com,https://your-api-domain.com
```

### Issue 2: "Failed to fetch"

**Solution:** Make sure:
1. Backend is running: `docker-compose ps`
2. URL is correct (https for production, http for local)
3. Your origin is in `ALLOWED_ORIGINS`

### Issue 3: CORS works locally but not on VPS

**Solution:** 
1. Use `https://` for production (not `http://`)
2. Update `ALLOWED_ORIGINS` with your VPS domain
3. Restart containers

```bash
docker-compose restart
```

### Issue 4: CORS error after SSL certificate

**Solution:** Update `ALLOWED_ORIGINS` to use `https://` instead of `http://`

```env
# Before
ALLOWED_ORIGINS=http://your-domain.com

# After (with SSL)
ALLOWED_ORIGINS=https://your-domain.com
```

---

## Advanced CORS Configuration

### Wildcard Domains (NOT recommended)

```env
# Allow all domains (testing only!)
ALLOWED_ORIGINS=*

# Allow all subdomains (more specific)
ALLOWED_ORIGINS=https://*.your-domain.com
```

### IP-based CORS

For VPS with static IP:

```env
# Your VPS IP
ALLOWED_ORIGINS=http://123.45.67.89:3000

# Or
ALLOWED_ORIGINS=https://123.45.67.89
```

---

## CORS Configuration in Code

The CORS is configured in `app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000,http://localhost:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
```

**Parameters:**
- `allow_origins`: List of allowed domains
- `allow_credentials`: Allow cookies/auth headers
- `allow_methods`: Allowed HTTP methods (GET, POST, etc.)
- `allow_headers`: Allowed request headers
- `expose_headers`: Headers visible to frontend

---

## Environment-specific Setup

### Development (.env.dev)
```env
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000
```

### Staging (.env.staging)
```env
ALLOWED_ORIGINS=https://staging.your-domain.com
```

### Production (.env.prod)
```env
ALLOWED_ORIGINS=https://your-domain.com,https://api.your-domain.com
```

---

## VPS Nginx Configuration with CORS

If using Nginx as reverse proxy, also add CORS headers there:

```nginx
location / {
    proxy_pass http://backend:8000;
    
    # CORS headers from backend (should be handled by FastAPI)
    add_header 'Access-Control-Allow-Origin' '$http_origin' always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range' always;
    
    if ($request_method = 'OPTIONS') {
        return 204;
    }
}
```

---

## Quick Reference

| Scenario | ALLOWED_ORIGINS |
|----------|-----------------|
| Local dev (React on 3000) | `http://localhost:3000,http://localhost:8000` |
| Local dev (Vite on 5173) | `http://localhost:5173,http://localhost:8000` |
| Single domain | `https://your-domain.com` |
| Multiple domains | `https://domain1.com,https://domain2.com` |
| With subdomains | `https://your-domain.com,https://api.your-domain.com` |
| Testing (allow all) | `*` |

---

## Deployment Checklist

- [ ] Update `.env` with your domain
- [ ] Rebuild Docker image: `docker-compose build --no-cache`
- [ ] Restart services: `docker-compose down && docker-compose up -d`
- [ ] Check CORS in logs: `docker-compose logs backend | grep CORS`
- [ ] Test from frontend
- [ ] Verify no CORS errors in browser console

---

**CORS is now configured and ready! Your frontend can communicate with the backend.** 🚀
