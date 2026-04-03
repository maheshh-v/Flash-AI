# Flash-AI VPS Deployment Guide
**Complete setup from scratch to production-ready**

---

## 📋 Prerequisites
- VPS with Ubuntu 22.04 LTS (or similar Linux)
- SSH access to root or sudo user
- Domain name (optional but recommended)
- 4GB+ RAM, 20GB+ storage recommended

---

## 🚀 STEP 1: Initial VPS Setup

### SSH into your VPS
```bash
ssh root@your_vps_ip
# or
ssh username@your_vps_ip
```

### Update system
```bash
apt update && apt upgrade -y
```

### Install basic dependencies
```bash
apt install -y \
  curl \
  wget \
  git \
  build-essential \
  python3-dev \
  python3-pip \
  python3-venv
```

---

## 🐳 STEP 2: Install Docker & Docker Compose

### Install Docker
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
```

### Add user to docker group (optional - run Docker without sudo)
```bash
usermod -aG docker $USER
newgrp docker
```

### Verify Docker installation
```bash
docker --version
docker-compose --version
```

---

## 📦 STEP 3: Clone Repository

### Choose deployment directory
```bash
cd /opt
# or
cd /home/$USER
```

### Clone the repository
```bash
git clone https://github.com/your-repo-url/Flash-AI.git
cd Flash-AI/Flash-AI
```

### Or if using SSH with git keys:
```bash
git clone git@github.com:your-username/Flash-AI.git
cd Flash-AI/Flash-AI
```

---

## 🔐 STEP 4: Create and Configure .env File

### Create .env file
```bash
cat > .env << 'EOF'
# ============================================================
# Cloudflare Workers AI (PRIMARY LLM)
# ============================================================
CF_API_TOKEN=your_cloudflare_api_token_here
CF_GATEWAY_URL=https://gateway.ai.cloudflare.com/v1/your_account_id/your_gateway/workers-ai
CF_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast
CF_EMBEDDING_MODEL=@cf/baai/bge-base-en-v1.5
LLM_TEMPERATURE=0.3

# ============================================================
# Google Gemini (FALLBACK LLM)
# ============================================================
GOOGLE_API_KEY=your_google_api_key_here

# ============================================================
# MongoDB
# ============================================================
# Option 1: Local MongoDB (via Docker)
MONGODB_URI=mongodb://mongo:27017

# Option 2: MongoDB Atlas Cloud
# MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority

MONGODB_DB_NAME=flashspace

# ============================================================
# Redis
# ============================================================
REDIS_URL=redis://redis:6379
REDIS_CACHE_ENABLED=true

# ============================================================
# Pinecone (Vector Search)
# ============================================================
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=flashspace-index
PINECONE_ENVIRONMENT=us-east-1

# ============================================================
# Authentication
# ============================================================
AUTH_SECRET_KEY=generate_a_random_secret_key_here_min_32_chars
PARTNER_API_KEY=your_partner_api_key

# ============================================================
# Application Settings
# ============================================================
ENVIRONMENT=production
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
EOF
```

### Secure the .env file
```bash
chmod 600 .env
```

### Generate secure secret key
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy output and paste in AUTH_SECRET_KEY in .env
```

### Edit .env with your actual keys
```bash
nano .env
# Or use vim if you prefer
# vim .env
```

### Configure CORS for your domain
```bash
# Edit the .env file and update ALLOWED_ORIGINS
# Change from:
# ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# To your domain(s):
# ALLOWED_ORIGINS=https://your-domain.com,https://api.your-domain.com
```

---

## ⚠️ IMPORTANT: CORS Configuration

Before deploying, update the CORS settings in `.env`:

```env
# For single domain
ALLOWED_ORIGINS=https://your-domain.com

# For multiple domains/subdomains
ALLOWED_ORIGINS=https://your-domain.com,https://api.your-domain.com,https://www.your-domain.com
```

**See `CORS_SETUP_GUIDE.md` for detailed CORS documentation.**

---

## 🐳 STEP 5: Build and Start Docker Services

### Build the Docker image (first time only)
```bash
docker-compose build
```

### Start all services in background
```bash
docker-compose up -d
```

### Verify services are running
```bash
docker-compose ps
```

### Expected output:
```
NAME               IMAGE              COMMAND                  SERVICE   STATUS         PORTS
flash-ai-backend   flash-ai-backend   "uvicorn app.main:ap…"   backend   Up 2 minutes   0.0.0.0:8000->8000/tcp
flash-ai-redis     redis:7-alpine     "docker-entrypoint.s…"   redis     Up 2 minutes   0.0.0.0:6379->6379/tcp
```

### Check backend logs for errors
```bash
docker-compose logs backend
```

---

## 🌐 STEP 6: Install and Configure Nginx (Reverse Proxy)

### Install Nginx
```bash
apt install -y nginx
```

### Create Nginx configuration file
```bash
cat > /etc/nginx/sites-available/flash-ai << 'EOF'
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    # Redirect HTTP to HTTPS (uncomment after SSL is ready)
    # return 301 https://$host$request_uri;

    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long-running requests
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffering
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
    }

    location /docs {
        proxy_pass http://backend/docs;
        proxy_set_header Host $host;
    }

    location /redoc {
        proxy_pass http://backend/redoc;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://backend/openapi.json;
        proxy_set_header Host $host;
    }
}
EOF
```

### Enable the site
```bash
ln -s /etc/nginx/sites-available/flash-ai /etc/nginx/sites-enabled/flash-ai
```

### Remove default site (optional but recommended)
```bash
rm /etc/nginx/sites-enabled/default
```

### Test Nginx configuration
```bash
nginx -t
```

### Should output:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### Start and enable Nginx
```bash
systemctl start nginx
systemctl enable nginx
```

### Verify Nginx is running
```bash
systemctl status nginx
```

---

## 🔒 STEP 7: SSL/TLS with Let's Encrypt (HTTPS)

### Install Certbot
```bash
apt install -y certbot python3-certbot-nginx
```

### Get SSL certificate (replace with your domain)
```bash
certbot --nginx -d your_domain.com
```

### Verify certificate installation
```bash
certbot certificates
```

### Auto-renewal should be enabled by default, verify:
```bash
systemctl status certbot.timer
```

### Test certificate renewal (dry run)
```bash
certbot renew --dry-run
```

---

## 🔄 STEP 8: Update Nginx for HTTPS (After SSL)

### Edit Nginx configuration
```bash
nano /etc/nginx/sites-available/flash-ai
```

### Replace with this HTTPS-ready config:
```nginx
upstream backend {
    server 127.0.0.1:8000;
}

# HTTP redirect to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name your_domain.com;
    
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name your_domain.com;

    # SSL certificates (auto-generated by Certbot)
    ssl_certificate /etc/letsencrypt/live/your_domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your_domain.com/privkey.pem;

    # SSL security settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
    }
}
```

### Test updated config
```bash
nginx -t
```

### Reload Nginx
```bash
systemctl reload nginx
```

---

## 🚀 STEP 9: Setup Auto-restart with Systemd

### Create systemd service file
```bash
cat > /etc/systemd/system/flash-ai.service << 'EOF'
[Unit]
Description=Flash-AI Backend Service
After=docker.service
Requires=docker.service
Documentation=https://github.com/your-repo/Flash-AI

[Service]
Type=simple
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=flash-ai

# Working directory
WorkingDirectory=/opt/Flash-AI/Flash-AI

# Start command
ExecStart=/usr/bin/docker-compose up

# Stop command
ExecStop=/usr/bin/docker-compose down

# User
User=root
# Or your deployment user:
# User=deploy

[Install]
WantedBy=multi-user.target
EOF
```

### Reload systemd daemon
```bash
systemctl daemon-reload
```

### Enable the service
```bash
systemctl enable flash-ai
```

### Start the service
```bash
systemctl start flash-ai
```

### Check status
```bash
systemctl status flash-ai
```

### View service logs
```bash
journalctl -u flash-ai -f
```

---

## 🔥 STEP 10: Configure Firewall

### Enable UFW (Ubuntu Firewall)
```bash
ufw enable
```

### Allow SSH
```bash
ufw allow 22/tcp
```

### Allow HTTP
```bash
ufw allow 80/tcp
```

### Allow HTTPS
```bash
ufw allow 443/tcp
```

### Optionally allow internal services (NOT recommended for production)
```bash
# Redis (only if needed externally)
# ufw allow 6379/tcp

# MongoDB (only if needed externally)
# ufw allow 27017/tcp
```

### Check firewall rules
```bash
ufw status
```

---

## 📊 STEP 11: Monitoring & Logging

### View Docker container logs
```bash
docker-compose logs backend
docker-compose logs redis
```

### Real-time logs with follow
```bash
docker-compose logs -f backend
```

### View specific number of lines
```bash
docker-compose logs --tail=100 backend
```

### Check Docker disk usage
```bash
docker system df
```

### View running processes
```bash
docker-compose ps
docker stats
```

---

## 🔄 STEP 12: Backup & Maintenance

### Create backup directory
```bash
mkdir -p /backups/flash-ai
```

### Backup .env file (SECURE!)
```bash
cp /opt/Flash-AI/Flash-AI/.env /backups/flash-ai/.env.backup
chmod 600 /backups/flash-ai/.env.backup
```

### Export Docker volumes
```bash
docker run --rm -v flash-ai-data:/data -v /backups/flash-ai:/backup \
  busybox tar czf /backup/docker-volumes-backup.tar.gz -C /data .
```

### Restart services
```bash
docker-compose restart
# or
systemctl restart flash-ai
```

### Update images (pull latest code)
```bash
git pull origin main
docker-compose build --no-cache
docker-compose up -d
```

---

## 🔍 STEP 13: Verification Checklist

### Verify services are running
```bash
docker-compose ps
```

### Test API is accessible
```bash
curl http://localhost:8000/docs
# or from another machine
curl https://your_domain.com/docs
```

### Check Nginx status
```bash
systemctl status nginx
```

### Check SSL certificate
```bash
certbot certificates
```

### Check firewall rules
```bash
ufw status
```

### Verify systemd service
```bash
systemctl status flash-ai
```

---

## 📝 Useful VPS Commands

### Stop all services
```bash
docker-compose stop
# or
systemctl stop flash-ai
```

### Start services
```bash
docker-compose start
# or
systemctl start flash-ai
```

### Restart services
```bash
docker-compose restart
# or
systemctl restart flash-ai
```

### Remove containers (keep images)
```bash
docker-compose down
```

### Remove everything (containers, images, volumes)
```bash
docker-compose down -v
```

### View resource usage
```bash
docker stats
docker system df
```

### SSH into running container
```bash
docker-compose exec backend bash
```

### View container logs
```bash
docker-compose logs [service-name]
```

### Pull latest code and redeploy
```bash
cd /opt/Flash-AI/Flash-AI
git pull origin main
docker-compose build
docker-compose up -d
```

---

## 🚨 Troubleshooting

### Port already in use (8000 or 6379)
```bash
# Find process using port
lsof -i :8000
lsof -i :6379

# Kill the process
kill -9 <PID>

# Or restart services
docker-compose restart
```

### Container won't start
```bash
# Check logs
docker-compose logs backend

# Recreate containers
docker-compose down
docker-compose up -d
```

### Nginx not working
```bash
# Test config
nginx -t

# Check status
systemctl status nginx

# View error logs
tail -f /var/log/nginx/error.log

# Restart
systemctl restart nginx
```

### Out of disk space
```bash
# Check usage
df -h

# Clean Docker
docker system prune -a --volumes

# View image sizes
docker images
```

### Memory issues
```bash
# Check memory usage
free -h

# Check container resource usage
docker stats

# Limit container memory in docker-compose.yml
```

---

## 🔐 Security Best Practices

1. **Keep SSH key secure** - Only SSH, no password login
2. **Use UFW firewall** - Only allow necessary ports
3. **Enable SSL/HTTPS** - Let's Encrypt (free)
4. **Secure .env file** - chmod 600, never commit
5. **Regular updates** - `apt update && apt upgrade -y`
6. **Backup database** - Regular MongoDB backups
7. **Monitor logs** - Check for errors and attacks
8. **Strong passwords** - Use 32+ character random keys
9. **Disable Redis externally** - Only internal connections
10. **Disable MongoDB externally** - Only internal connections

---

## 📞 Quick Reference

| Task | Command |
|------|---------|
| Deploy | `docker-compose up -d` |
| Stop | `docker-compose down` |
| Logs | `docker-compose logs -f backend` |
| Status | `docker-compose ps` |
| Restart | `docker-compose restart` |
| Update | `git pull && docker-compose build && docker-compose up -d` |
| SSH into container | `docker-compose exec backend bash` |
| View Nginx logs | `tail -f /var/log/nginx/access.log` |
| Renew SSL | `certbot renew` |
| Check firewall | `ufw status` |

---

## 🎯 Complete Deployment Command Chain (Copy-Paste)

```bash
# 1. SSH to VPS
ssh root@your_vps_ip

# 2. Update system
apt update && apt upgrade -y

# 3. Install dependencies
apt install -y curl wget git build-essential python3-dev python3-pip python3-venv

# 4. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh

# 5. Add user to docker group
usermod -aG docker $USER && newgrp docker

# 6. Clone repo
cd /opt && git clone https://github.com/your-repo-url/Flash-AI.git && cd Flash-AI/Flash-AI

# 7. Create .env (edit with your values!)
nano .env

# 8. Start services
docker-compose up -d

# 9. Install Nginx
apt install -y nginx certbot python3-certbot-nginx

# 10. Configure Nginx
cat > /etc/nginx/sites-available/flash-ai << 'EOF'
upstream backend { server 127.0.0.1:8000; }
server {
    listen 80;
    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

# 11. Enable Nginx
ln -s /etc/nginx/sites-available/flash-ai /etc/nginx/sites-enabled/flash-ai && nginx -t && systemctl restart nginx

# 12. Get SSL certificate
certbot --nginx -d your_domain.com

# 13. Setup auto-restart
cat > /etc/systemd/system/flash-ai.service << 'EOF'
[Unit]
Description=Flash-AI Backend
After=docker.service
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=10
WorkingDirectory=/opt/Flash-AI/Flash-AI
ExecStart=/usr/bin/docker-compose up
ExecStop=/usr/bin/docker-compose down

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload && systemctl enable flash-ai && systemctl start flash-ai

# 14. Setup firewall
ufw enable && ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp

# 15. Verify deployment
docker-compose ps && curl https://your_domain.com/docs

echo "✅ Flash-AI successfully deployed!"
```

---

**Your Flash-AI is now production-ready! 🚀**
