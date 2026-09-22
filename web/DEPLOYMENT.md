# Marketplace Web UI - Deployment Guide

This guide covers deploying the Corvin Marketplace web UI to various platforms.

## Table of Contents

1. [Local Development](#local-development)
2. [Docker Deployment](#docker-deployment)
3. [Cloud Platforms](#cloud-platforms)
4. [Self-Hosted](#self-hosted)
5. [Static Export](#static-export)
6. [CI/CD Integration](#cicd-integration)
7. [Monitoring & Troubleshooting](#monitoring--troubleshooting)

## Local Development

### Prerequisites
- Node.js 18+ (check with `node -v`)
- npm 9+ (check with `npm -v`)

### Setup

```bash
cd web
npm install
npm run dev
```

Visit `http://localhost:3001` in your browser.

**Features:**
- ✅ Hot module reloading
- ✅ Full source maps for debugging
- ✅ TypeScript error checking
- ✅ Automatic CORS for local APIs

### Environment Variables

Create `.env.local` in the `web/` directory:

```env
# Development
NODE_ENV=development

# Optional: Debug logging
DEBUG=*

# Optional: Plugin data path
PLUGIN_DATA_PATH=../../index/plugins.json
```

## Docker Deployment

### Quick Start

```bash
# Build image
docker build -t corvin-marketplace-web:latest .

# Run container
docker run -d \
  --name marketplace-web \
  -p 3001:3001 \
  -e NODE_ENV=production \
  corvin-marketplace-web:latest

# View logs
docker logs -f marketplace-web
```

### Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

This includes:
- Next.js marketplace application
- Optional Nginx reverse proxy
- Health checks
- Volume mounts for live plugin updates

### Production Optimization

For production Docker builds:

```bash
# Build with caching
docker build --no-cache -t corvin-marketplace-web:v1.0.0 .

# Tag for registry
docker tag corvin-marketplace-web:v1.0.0 registry.example.com/corvin/marketplace:v1.0.0

# Push to registry
docker push registry.example.com/corvin/marketplace:v1.0.0
```

Kubernetes deployment example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: corvin-marketplace-web
spec:
  replicas: 3
  selector:
    matchLabels:
      app: corvin-marketplace-web
  template:
    metadata:
      labels:
        app: corvin-marketplace-web
    spec:
      containers:
      - name: marketplace-web
        image: registry.example.com/corvin/marketplace:v1.0.0
        ports:
        - containerPort: 3001
        env:
        - name: NODE_ENV
          value: "production"
        livenessProbe:
          httpGet:
            path: /
            port: 3001
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 3001
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
```

## Cloud Platforms

### Vercel (Easiest)

Vercel is optimized for Next.js and offers:
- Free tier (great for testing)
- Automatic deployments from GitHub
- Built-in CDN & caching
- Environment variable management
- Serverless functions

**Setup:**

1. Install Vercel CLI: `npm i -g vercel`
2. Deploy: `vercel deploy`
3. Connect to GitHub for automatic deploys

**Configuration** (`vercel.json`):

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "env": {
    "NODE_ENV": "production"
  }
}
```

### Netlify

**Option 1: GitHub Integration**
1. Push code to GitHub
2. Connect repository at netlify.com
3. Set build command: `npm run build`
4. Set publish directory: `.next`

**Option 2: Manual Deploy**
```bash
npm run export
# Upload 'out/' directory to Netlify
```

### AWS Amplify

```bash
# Install Amplify CLI
npm install -g @aws-amplify/cli

# Initialize
amplify init

# Deploy
amplify publish
```

### Heroku

```bash
# Login
heroku login

# Create app
heroku create corvin-marketplace

# Deploy
git push heroku main

# View logs
heroku logs --tail
```

**Procfile:**
```
web: npm run build && npm start
```

### DigitalOcean App Platform

1. Connect GitHub repository
2. Set build command: `npm run build`
3. Set run command: `npm start`
4. Configure environment: `NODE_ENV=production`
5. Deploy

## Self-Hosted

### Linux (Ubuntu/Debian)

**Prerequisites:**
```bash
# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install PM2 (process manager)
npm install -g pm2
```

**Deployment:**
```bash
# Clone or pull latest code
cd /var/www/corvin-marketplace/web
git pull origin main

# Install dependencies
npm install --production

# Build for production
npm run build

# Start with PM2
pm2 start npm --name marketplace --cwd /var/www/corvin-marketplace/web -- start

# Save PM2 config
pm2 save

# Enable auto-restart on reboot
pm2 startup
```

**Nginx Reverse Proxy:**

```bash
# Copy and edit nginx config
sudo cp nginx.conf.example /etc/nginx/sites-available/marketplace
sudo nano /etc/nginx/sites-available/marketplace
sudo ln -s /etc/nginx/sites-available/marketplace /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

**SSL/HTTPS (Let's Encrypt):**

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Generate certificate
sudo certbot certonly --nginx -d marketplace.corvin.local

# Auto-renew (already enabled)
sudo certbot renew --dry-run
```

### macOS

```bash
# Install Node.js
brew install node

# Install and configure PM2
npm install -g pm2
pm2 start npm --name marketplace -- start

# Start on login
pm2 startup
```

## Static Export

For static hosting (GitHub Pages, S3, Cloudflare Pages, etc.):

```bash
# Generate static files
npm run export

# Output directory: out/
# Upload to your static hosting service
```

**GitHub Pages:**
```bash
# Push 'out' directory to gh-pages branch
git subtree push --prefix out origin gh-pages
```

**AWS S3 + CloudFront:**
```bash
# Build
npm run export

# Sync to S3
aws s3 sync out/ s3://corvin-marketplace/ --delete

# Invalidate CloudFront
aws cloudfront create-invalidation --distribution-id E123 --paths "/*"
```

## CI/CD Integration

### GitHub Actions

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy Marketplace

on:
  push:
    branches: [main]
    paths:
      - 'web/**'
  pull_request:
    branches: [main]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
          cache: 'npm'
      
      - run: cd web && npm install
      
      - run: cd web && npm run lint
      
      - run: cd web && npm run build
      
      - name: Build Docker image
        if: github.event_name == 'push'
        run: |
          docker build -t corvin-marketplace-web:${{ github.sha }} web/
          docker tag corvin-marketplace-web:${{ github.sha }} corvin-marketplace-web:latest
      
      - name: Push to registry
        if: github.event_name == 'push'
        run: |
          echo "${{ secrets.REGISTRY_PASSWORD }}" | docker login -u "${{ secrets.REGISTRY_USER }}" --password-stdin
          docker push corvin-marketplace-web:${{ github.sha }}
```

### GitLab CI

Create `.gitlab-ci.yml`:

```yaml
stages:
  - build
  - test
  - deploy

build:
  image: node:18-alpine
  stage: build
  script:
    - cd web
    - npm install
    - npm run build
  artifacts:
    paths:
      - web/.next
      - web/node_modules

deploy:production:
  image: docker:latest
  stage: deploy
  only:
    - main
  script:
    - docker build -t marketplace:$CI_COMMIT_SHA web/
    - docker push registry.example.com/marketplace:$CI_COMMIT_SHA
```

## Monitoring & Troubleshooting

### Health Checks

```bash
# Test if server is running
curl http://localhost:3001/

# Check API endpoint
curl http://localhost:3001/api/plugins

# Check specific plugin
curl http://localhost:3001/api/plugins/plugin:buildin-example
```

### Performance Monitoring

```bash
# Build size analysis
npm run build -- --analyze

# Runtime profiling (with Node.js)
node --prof web/.next/standalone/server.js
node --prof-process isolate-*.log > profile.txt
```

### Logs

```bash
# Docker logs
docker logs -f marketplace-web

# PM2 logs
pm2 logs marketplace

# Systemd logs (if using systemd)
journalctl -u corvin-marketplace -f
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Port 3001 in use | `lsof -i :3001` to find process, or use different port |
| Out of memory | Increase Node.js heap: `NODE_OPTIONS="--max-old-space-size=4096"` |
| Plugins not loading | Check `/index/plugins.json` path, verify JSON is valid |
| Slow builds | Check disk I/O, increase build cache size |
| SSL/HTTPS issues | Verify certificates with `openssl s_client -connect host:443` |

### Backup & Recovery

```bash
# Backup data
tar -czf marketplace-backup-$(date +%Y%m%d).tar.gz web/ index/ plugins/

# Restore from backup
tar -xzf marketplace-backup-20240101.tar.gz
```

## Security Checklist

- [ ] Enable HTTPS/SSL
- [ ] Set secure HTTP headers (CSP, X-Frame-Options, etc.)
- [ ] Use environment variables for secrets
- [ ] Keep dependencies updated: `npm audit fix`
- [ ] Enable rate limiting on API endpoints
- [ ] Set up DDoS protection (Cloudflare, AWS Shield)
- [ ] Regular security audits: `npm audit`
- [ ] Monitor for vulnerable dependencies

## Performance Optimization

1. **Enable Compression**: Gzip enabled by default in nginx config
2. **Caching**: Leverage CDN for static assets
3. **Database**: Cache plugins.json in Redis for production
4. **Lazy Loading**: Images load on scroll
5. **Code Splitting**: Automatic with Next.js
6. **Minification**: Enabled in production builds

## Support & Documentation

- [Next.js Deployment](https://nextjs.org/docs/deployment/introduction)
- [Node.js Best Practices](https://nodejs.org/en/docs/guides/)
- [Docker Documentation](https://docs.docker.com/)
- [Nginx Documentation](https://nginx.org/en/docs/)

## Summary

Choose your deployment method based on your needs:

- **Development**: `npm run dev`
- **Testing**: Docker Compose
- **Production**: Vercel, AWS, or self-hosted with Nginx
- **Static Hosting**: `npm run export` → GitHub Pages, S3, Cloudflare
- **Scaling**: Kubernetes with Docker images

Questions? Check logs, review this guide, or file an issue in the repository.
