# 🆘 JWT Authentication Troubleshooting (Hinglish)

## Problem: Login Ke Saath API Fail Ho Raha Hai

### 🔍 Diagnosis Guide

#### **Error 1: HTTP 401 - Unauthorized**
```
Matlab: Token invalid hai ya expire ho gya
```

**Check Karo:**
1. Token format: `Authorization: Bearer eyJ...` (Bearer ka space!?)
2. Token expiry: Token still valid hai?
3. JWT_SECRET: Frontend aur Backend same hai?

**Fix:**
```bash
# Backend logs dekho
docker-compose logs backend --tail=20 | grep -i "signature\|expired"

# Agar "Signature verification failed" likha hai:
# → JWT_SECRET mismatch hai!
# Frontend secret aur backend secret same karo
```

---

#### **Error 2: HTTP 403 - Forbidden**
```
Matlab: Token valid hai lekin user ko permission nahi
```

**Check Karo:**
1. Token mein role kya hai? (admin, user, partner?)
2. Endpoint ko kaunsi role chahiye?

**Fix:**
```bash
# Backend logs dekho
docker-compose logs backend --tail=20 | grep "Role not allowed"

# Solution: Token mein role add karo ya endpoint ke permissions change karo
```

---

#### **Error 3: HTTP 500 - Internal Server Error**
```
Matlab: Backend mein problem hai
```

**Debug:**
```bash
# Complete error dekho
docker-compose logs backend --tail=50

# Possible issues:
# - JWT library import failed
# - Secret key empty hai
# - Token format galat hai
```

---

### 🧪 Step-by-Step Testing

#### **Step 1: Token Decode Test**
```python
# Python script banao test karne ke liye:

import jwt
import os

TOKEN = "your-jwt-token-here"
SECRET = os.getenv("JWT_SECRET", "dev-secret")

try:
    payload = jwt.decode(TOKEN, SECRET, algorithms=["HS256"])
    print("✅ Token Valid!")
    print(f"   Payload: {payload}")
except jwt.ExpiredSignatureError:
    print("❌ Token Expired!")
except jwt.InvalidTokenError as e:
    print(f"❌ Token Invalid: {e}")
```

**Run:**
```bash
cd /opt/Flash-AI/Flash-AI
python3 << 'EOF'
# Paste above code
EOF
```

#### **Step 2: Header Check**
```bash
# Frontend network tab mein dekho:
# Request headers mein yeh hona chahiye:

Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
              ^^^^^^ (Space important!)
```

#### **Step 3: Token Payload Inspection**
```javascript
// Browser console mein:

// Token decode (online tool use karo ya):
function parseJwt(token) {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => 
        '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
    ).join(''));
    return JSON.parse(jsonPayload);
}

const token = "your-token";
console.log(parseJwt(token));

// Output example:
// {
//   user_id: "user_123",
//   tenant_id: "tenant_456",
//   role: "user",
//   iat: 1712158800,
//   exp: 1712245200
// }
```

---

### 🛠️ Common Fixes Checklist

- [ ] **Frontend aur Backend JWT_SECRET same hai?**
  ```bash
  # Frontend check karo (apne website ka code)
  grep -r "JWT_SECRET\|sign.*secret" src/
  
  # Backend check karo
  grep JWT_SECRET .env
  # Agar different hai toh backend .env update karo
  ```

- [ ] **Token format correct hai?**
  ```javascript
  // ✅ Sahi format:
  Authorization: Bearer eyJhbGc...
  
  // ❌ Galat formats:
  Authorization: eyJhbGc...          (Bearer missing)
  Authorization: bearer eyJhbGc...   (lowercase 'bearer')
  Bearer eyJhbGc...                  (no Authorization header)
  ```

- [ ] **Token mein required claims hain?**
  ```bash
  # Backend .env dekho
  grep JWT_*_CLAIM .env
  
  # Output example:
  JWT_USER_CLAIM=user_id
  JWT_TENANT_CLAIM=tenant_id
  JWT_ROLE_CLAIM=role
  
  # Token mein yeh claims ZAROORI hain!
  # Agar nahi hain toh frontend token generation fix karo
  ```

- [ ] **Token expire nahi ho gya?**
  ```bash
  # Token payload dekho (browser console me)
  const payload = parseJwt(token);
  console.log("Expires at:", new Date(payload.exp * 1000));
  ```

- [ ] **Backend properly restarted hai?**
  ```bash
  docker-compose restart backend
  sleep 5
  docker-compose logs backend --tail=5
  ```

- [ ] **DEV_AUTH_BYPASS disabled hai?**
  ```bash
  grep DEV_AUTH_BYPASS .env
  # Should be: DEV_AUTH_BYPASS=false
  # If true, JWT validation skip hota hai (production mein nahi chalega!)
  ```

---

### 🔴 Emergency Fixes

#### **Agar PURA Broken Ho Gya:**

```bash
# 1. Backup .env
cp .env .env.backup

# 2. Reset to defaults
cat > .env << 'EOF'
DEV_AUTH_BYPASS=true              # Temporarily enable bypass
JWT_SECRET=dev-secret-change-me
JWT_ALGORITHM=HS256
JWT_USER_CLAIM=user_id
JWT_TENANT_CLAIM=tenant_id
JWT_ROLE_CLAIM=role
EOF

# 3. Restart
docker-compose restart backend

# 4. Test
curl -i https://your-domain.com/docs

# Agar ab work ho rahe ho toh:
# - Frontend aur backend ke JWT settings match karo
# - Phir DEV_AUTH_BYPASS=false karo
```

#### **Agar Frontend Ka Token Invalid Tha:**

```bash
# Frontend mein token generation fix karo:

// ❌ Galat (missing claims):
const token = jwt.sign({ user_id: "123" }, SECRET);

// ✅ Sahi (all claims):
const token = jwt.sign({
  user_id: "user_123",
  tenant_id: "tenant_456", 
  role: "user"
}, SECRET, { expiresIn: '7d' });
```

---

### 📊 Decision Tree

```
API gives error → Check Status Code
                  ├─ 401 (Unauthorized)
                  │  ├─ Token invalid? (Signature verification failed)
                  │  │  └─ Fix JWT_SECRET
                  │  ├─ Token expired?
                  │  │  └─ Generate new token
                  │  └─ Bearer format wrong?
                  │     └─ Send "Bearer TOKEN"
                  │
                  ├─ 403 (Forbidden)
                  │  ├─ Role not allowed?
                  │  │  └─ Check token role vs endpoint requirements
                  │  └─ Tenant mismatch?
                  │     └─ Check tenant_id in token
                  │
                  └─ 500 (Server Error)
                     ├─ JWT decoding crash?
                     │  └─ Check JWT library installation
                     ├─ Secret key empty?
                     │  └─ Update .env
                     └─ Token payload malformed?
                        └─ Check token claims
```

---

### 💬 Jab Bhi Stuck Ho:

**VPS par SSH karke yeh commands run karo:**

```bash
cd /opt/Flash-AI/Flash-AI

# 1. Current config
echo "=== JWT Config ===" && grep JWT .env

# 2. Last 30 errors
echo "=== Backend Errors ===" && \
  docker-compose logs backend --tail=30 | grep -E "error|jwt|auth|401|403|500"

# 3. Test without token
echo "=== Test (No Token) ===" && \
  curl -i https://your-domain.com/docs 2>&1 | head -5

# 4. Test with token (put actual token)
echo "=== Test (With Token) ===" && \
  curl -i -H "Authorization: Bearer ACTUAL_TOKEN_HERE" \
    https://your-domain.com/docs 2>&1 | head -10
```

**Yeh output mujhe share karo aur fix kar dunga! 🚀**

---

## 🎯 Final Checklist

- [ ] Frontend se JWT token bhej rahe ho? (Authorization header mein)
- [ ] Token format: `Authorization: Bearer eyJ...`?
- [ ] Backend .env mein DEV_AUTH_BYPASS=false?
- [ ] JWT_SECRET frontend aur backend mein same?
- [ ] Token mein user_id, tenant_id, role claims hain?
- [ ] Token expire nahi ho gya?
- [ ] Backend recently restart kiya?
- [ ] CORS properly configured?
- [ ] Logs check kiye?

**Agar sab check kar liya aur phir bhi problem hai toh mujhe batao! 🆘**
