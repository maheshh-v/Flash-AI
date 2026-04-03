# Authentication Setup Guide

## 🔐 Problem Fixed

Your API was returning **401 Unauthorized "Missing Authorization header"** because:
1. The authentication logic had a bug (duplicate null check)
2. Required JWT bearer token for all endpoints
3. No fallback for development/guest access

---

## ✅ Current Solution (Development Mode)

**Development Mode is now ENABLED** with `DEV_AUTH_BYPASS=true` in `.env`:

```env
DEV_AUTH_BYPASS=true
DEV_USER_ID=test_user
DEV_TENANT_ID=test_tenant
DEV_ROLE=admin
```

### What This Means:
✅ All API calls work **without authentication headers**
✅ Backend bypasses JWT validation
✅ Auto-assigned as admin user for testing
✅ Perfect for development and testing

---

## ⚠️ IMPORTANT: Production Setup

**NEVER deploy to production with `DEV_AUTH_BYPASS=true`!**

Follow these steps for production:

### Option 1: Disable Auth Bypass (Recommended)

```env
DEV_AUTH_BYPASS=false
```

Then use one of the authentication methods below.

### Option 2: Generate JWT Token

```bash
# Install PyJWT
pip install PyJWT

# Generate a test token
python3 << 'EOF'
import jwt
import json
from datetime import datetime, timedelta

secret = "your_jwt_secret_from_env"
payload = {
    "user_id": "user123",
    "tenant_id": "tenant456",
    "role": "admin",
    "iat": datetime.utcnow(),
    "exp": datetime.utcnow() + timedelta(hours=24)
}

token = jwt.encode(payload, secret, algorithm="HS256")
print(f"Authorization: Bearer {token}")
EOF
```

Then send requests with the header:
```bash
curl -H "Authorization: Bearer your_token_here" http://your-api.com/chat
```

### Option 3: Guest Access (No Auth)

Allow guest access by sending requests without Authorization header:
```bash
curl http://your-api.com/chat
```

The backend will auto-assign:
- `user_id: "guest"`
- `tenant_id: "public"` (from `GUEST_TENANT_ID` env)
- `role: "guest"`

---

## 🔧 Configuration Options

### Development (.env.dev)
```env
DEV_AUTH_BYPASS=true
DEV_USER_ID=dev_user
DEV_TENANT_ID=dev_tenant
DEV_ROLE=admin
```

### Production (.env.prod)
```env
DEV_AUTH_BYPASS=false
JWT_SECRET=your-secure-random-secret-here
JWT_ALGORITHM=HS256
JWT_USER_CLAIM=user_id
JWT_TENANT_CLAIM=tenant_id
JWT_ROLE_CLAIM=role
GUEST_TENANT_ID=public
```

---

## 🧪 Test API With/Without Auth

### Test 1: Without Auth (Development Mode)
```bash
# Should work with DEV_AUTH_BYPASS=true
curl http://localhost:8000/docs

# Response: 200 OK
```

### Test 2: With Bearer Token
```bash
curl -H "Authorization: Bearer your_jwt_token" \
     http://localhost:8000/chat \
     -d '{"query": "test"}'
```

### Test 3: Browser Console
```javascript
// Without auth (dev mode)
fetch('http://localhost:8000/docs')
  .then(r => r.text())
  .then(d => console.log('✅ Working!'))

// With auth
fetch('http://localhost:8000/docs', {
  headers: {
    'Authorization': 'Bearer eyJhbGc...'
  }
})
```

---

## 📋 Supported Roles

```python
allowed_roles = {"user", "admin", "partner", "affiliate", "sales", "guest"}
```

Each role can have different permissions configured in your app logic.

---

## 🚀 JWT Token Generation Script

Create `generate_token.py`:

```python
#!/usr/bin/env python3
import jwt
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def generate_token(
    user_id: str,
    tenant_id: str,
    role: str,
    secret: str = None,
    hours: int = 24
) -> str:
    """Generate a JWT token for testing"""
    
    if not secret:
        secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
    
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=hours)
    }
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token

if __name__ == "__main__":
    # Generate a test token
    token = generate_token(
        user_id="test_user",
        tenant_id="test_org",
        role="admin"
    )
    
    print("✅ Token Generated:")
    print(f"\nBearer: {token}")
    print(f"\nUse in requests as:")
    print(f"curl -H 'Authorization: Bearer {token}' http://your-api.com/chat")
    
    # Decode to show payload
    decoded = jwt.decode(token, os.getenv("JWT_SECRET", "dev-secret-change-me"), algorithms=["HS256"])
    print(f"\nPayload:")
    print(json.dumps(decoded, indent=2, default=str))
```

**Usage:**
```bash
python generate_token.py
```

---

## 🔐 Production Checklist

- [ ] Set `DEV_AUTH_BYPASS=false`
- [ ] Generate secure `JWT_SECRET` (32+ random chars)
- [ ] Implement JWT token generation endpoint or use external auth provider
- [ ] Set appropriate `GUEST_TENANT_ID` or disable guest access
- [ ] Test with valid JWT tokens
- [ ] Monitor logs for auth failures
- [ ] Document your authentication flow for clients
- [ ] API keys/tokens never logged or exposed
- [ ] Use HTTPS only in production

---

## 📚 Authentication Flow

```
1. Client sends request
   ↓
2. Check DEV_AUTH_BYPASS
   ├─ If true → Auto-assign admin credentials (DEV ONLY)
   └─ If false → Check for Authorization header
        ↓
3a. No Authorization header
    └─ Use guest credentials (user_id="guest", role="guest")
        ↓
3b. Has Authorization: Bearer header
    ├─ Validate bearer scheme
    ├─ Decode JWT token
    ├─ Extract claims (user_id, tenant_id, role)
    ├─ Validate role is allowed
    └─ Use decoded credentials
        ↓
4. Request proceeds with auth context
```

---

## 🆘 Troubleshooting

### Still Getting 401 Error?

1. **Check .env**
   ```bash
   grep DEV_AUTH_BYPASS .env
   # Should show: DEV_AUTH_BYPASS=true (or false for production)
   ```

2. **Restart containers**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

3. **Check logs for auth warnings**
   ```bash
   docker-compose logs backend | grep -i "auth\|bypass"
   ```

4. **Verify token format** (if using auth)
   ```bash
   # Token should start with "eyJ"
   # Format: Authorization: Bearer eyJ...
   ```

### 401 with correct token?

1. Verify JWT secret matches between token generation and backend
2. Check token expiration: `exp` claim should be in future
3. Ensure all required claims present: `user_id`, `tenant_id`, `role`
4. Validate role is in allowed list

---

## 🔄 Transition from Dev to Production

### Step 1: Generate Secure Secret
```bash
# Linux/Mac
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Windows PowerShell
[Convert]::ToBase64String((1..32 | ForEach-Object {[byte](Get-Random -Max 256)}))
```

### Step 2: Update .env
```env
# Disable dev mode
DEV_AUTH_BYPASS=false

# Set secure secret
JWT_SECRET=your_generated_secret_here
```

### Step 3: Implement Auth Endpoint
Create endpoint to issue tokens to authenticated users:

```python
@app.post("/auth/token")
async def get_token(username: str, password: str):
    # Verify username/password against your auth system
    # Generate JWT token
    # Return token to client
    pass
```

### Step 4: Update Clients
Frontend should:
1. Authenticate with `/auth/token`
2. Receive JWT token
3. Store token (localStorage/sessionStorage)
4. Send token in all API requests:
   ```javascript
   const token = localStorage.getItem('auth_token');
   fetch(url, {
     headers: {
       'Authorization': `Bearer ${token}`
     }
   })
   ```

---

## 📞 Environment Variables Reference

| Variable | Dev | Prod | Purpose |
|----------|-----|------|---------|
| `DEV_AUTH_BYPASS` | `true` | `false` | Skip auth validation |
| `DEV_USER_ID` | `test_user` | - | Dev auth user ID |
| `DEV_TENANT_ID` | `test_tenant` | - | Dev auth tenant ID |
| `DEV_ROLE` | `admin` | - | Dev auth role |
| `JWT_SECRET` | optional | ✅ required | Token signing key |
| `JWT_ALGORITHM` | - | `HS256` | Token algorithm |
| `JWT_USER_CLAIM` | - | `user_id` | User ID claim name |
| `JWT_TENANT_CLAIM` | - | `tenant_id` | Tenant ID claim name |
| `JWT_ROLE_CLAIM` | - | `role` | Role claim name |
| `GUEST_TENANT_ID` | `public` | `public` | Guest tenant ID |

---

## 🎯 Next Steps

1. **For Development**: You're all set! API works without auth.
2. **For Production**: Disable `DEV_AUTH_BYPASS` and implement proper JWT handling
3. **For Deployment**: See VPS_DEPLOYMENT_GUIDE.md for full setup

---

**Your Flash-AI API authentication is now configured! 🔐**
