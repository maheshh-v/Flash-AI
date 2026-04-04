# 🔐 JWT Authentication Guide (Hinglish)

## Problem 🔴
- ✅ **Bina Login** - Kaam kar raha hai (guest mode chalra hai)
- ❌ **Login Ke Saath** - Token bhej rahe ho lekin fail ho raha hai

---

## Root Causes (Samasyaein) 🤔

### 1. **JWT_SECRET Match Nahi Ho Raha** 
```
Frontend ne token ko ENCODE karte waqt:
  - Secret: "my-super-secret-key"
  
Backend decode kar rahe hain:
  - Secret: "different-secret"
  
Result: ❌ TOKEN DECODE FAIL!
```

### 2. **Token Format Galat**
```
Frontend bhej rahe hain:
  ❌ "eyJhbGc..." (sirf token)
  ✅ "Bearer eyJhbGc..." (Bearer ke saath)
```

### 3. **Token Mein Claims Nahi Hain**
```
Token mein zaroori se hona chahiye:
  ✅ user_id: "user_123"
  ✅ tenant_id: "tenant_456"
  ✅ role: "user"
  
Agar ye nahi hain toh decode fail hoga!
```

---

## ✅ Checklist - Yeh Karo VPS Par (SSH Karke):

### **Step 1: .env File Check Karo**
```bash
cd /opt/Flash-AI/Flash-AI
cat .env | grep -E "JWT|DEV_AUTH"
```

**Expected Output:**
```env
DEV_AUTH_BYPASS=false          # ✅ PRODUCTION MODE
JWT_SECRET=your-secret-key     # ✅ KUCH SECURE HONA CHAHIYE
JWT_ALGORITHM=HS256
JWT_USER_CLAIM=user_id
JWT_TENANT_CLAIM=tenant_id
JWT_ROLE_CLAIM=role
```

### **Step 2: Agar DEV_AUTH_BYPASS=true Hai**
```bash
# PROBLEM: Bypass enabled hai!
# Frontend JWT token ko IGNORE kar rahe ho backend

# FIX: Disable Karo
nano .env
# Change: DEV_AUTH_BYPASS=true → DEV_AUTH_BYPASS=false

# Save Karo (Ctrl+O, Enter, Ctrl+X)
```

### **Step 3: Backend Restart Karo**
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Wait 5 seconds
sleep 5

# Logs Dekho
docker-compose logs backend --tail=20
```

---

## 🧪 Test Karo - Token Ke Saath:

### **Option 1: Browser Console Se**
```javascript
// Apne website se browser console open karo (F12)
// Apna JWT token copy karo (localStorage se ya cookies se)

fetch('https://your-domain.com/docs', {
  headers: {
    'Authorization': 'Bearer YOUR_JWT_TOKEN_HERE'
  }
})
.then(r => r.json())
.then(data => {
  console.log('✅ Success:', data);
})
.catch(e => {
  console.log('❌ Error:', e);
});
```

### **Option 2: cURL Se (Terminal)**
```bash
TOKEN="your-jwt-token-here"
curl -v \
  -H "Authorization: Bearer $TOKEN" \
  https://your-domain.com/docs
```

**Output Dekho:**
- ✅ `HTTP/2 200` - Token valid hai!
- ❌ `HTTP/2 401` - Token invalid hai (secret match nahi)
- ❌ `HTTP/2 500` - Backend error (logs dekho)

---

## 🔍 Backend Logs Check Karo:

```bash
# Real-time logs
docker-compose logs backend -f

# Last 50 lines with grep
docker-compose logs backend --tail=50 | grep -E "auth|jwt|token|error"
```

**Expected Good Logs (✅):**
```
🔐 Received token, length: 250
🔑 Attempting to decode JWT token with algorithm: HS256
📋 Decoded JWT claims: user_id=user_123, tenant_id=tenant_456, role=user
✅ User authenticated successfully: user_id=user_123, role=user
```

**Expected Bad Logs (❌):**
```
❌ Invalid JWT token: Signature verification failed
  Token starts with: eyJhbGc...
  Secret length: 16

🔴 JWT decode failed: Invalid signature
```

---

## 🛠️ Common Fixes:

### **Problem: Signature Verification Failed**
**Matlab:** JWT_SECRET frontend aur backend mein alag hai

**Fix:**
```bash
# 1. Frontend ko kaunsa secret use kar rahe ho?
#    (Apne website/app mein dekho)

# 2. Backend .env mein same secret dalo
nano .env
JWT_SECRET=same-secret-as-frontend

# 3. Restart
docker-compose restart backend
```

### **Problem: Missing Claims**
**Matlab:** Token mein user_id nahi hai

**Fix:**  
```javascript
// Frontend mein token banate waqt yaad rakhna:

const token = jwt.sign({
  user_id: "user_123",      // ✅ ZAROORI
  tenant_id: "tenant_456",  // ✅ ZAROORI
  role: "user"              // ✅ ZAROORI
}, SECRET, { expiresIn: '7d' });
```

### **Problem: Token Expired**
**Matlab:** Token ki expiry time pass ho gya

**Fix:**
```bash
# Backend logs mein dekho:
⏰ JWT token expired

# Solution: Frontend se naya token generate karo ya refresh karo
```

---

## 🚀 Final Checklist:

- [ ] VPS SSH connection test
- [ ] `.env` mein `DEV_AUTH_BYPASS=false` set kiya
- [ ] `.env` mein `JWT_SECRET` frontend ke saath match hai
- [ ] Backend restart kiya (`docker-compose restart`)
- [ ] Browser console se test kiya
- [ ] Logs dekhe aur error samjhe
- [ ] Token format correct hai (`Bearer eyJ...`)

---

## 📞 Agar Phir Bhi Problem Ho:

```bash
# Complete debug info bhejne ke liye:

cd /opt/Flash-AI/Flash-AI

echo "=== Current Config ==="
grep -E "JWT|DEV_AUTH" .env

echo "=== Recent Errors ==="
docker-compose logs backend --tail=50 | grep -i "error\|auth\|jwt"

echo "=== Test Without Token ==="
curl -i https://your-domain.com/docs | head -10

echo "=== Test With Token (replace TOKEN) ==="
TOKEN="your-token-here"
curl -i -H "Authorization: Bearer $TOKEN" https://your-domain.com/docs | head -10
```

**Yeh output share karo toh fix kar dunga! 🚀**

---

## 🎯 Summary:

| Problem | Cause | Fix |
|---------|-------|-----|
| Login nahi ho raha | DEV_AUTH_BYPASS=true | `DEV_AUTH_BYPASS=false` karo |
| Token invalid error | JWT_SECRET match nahi | Frontend aur backend secret same karo |
| Missing claims error | Token mein user_id/role nahi | Frontend mein token create karte waqt claims add karo |
| Token expired error | Expiry time pass ho gya | Frontend se naya token generate karo |

**Kuch bhi problem ho toh mujhe batao! 🔧✅**
