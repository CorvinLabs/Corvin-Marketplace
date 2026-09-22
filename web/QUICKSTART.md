# Marketplace Web UI - Quick Start Guide

## One-Time Setup (5 minutes)

```bash
# Navigate to the web directory
cd /home/shumway/projects/Corvin-Marketplace/web

# Install dependencies
npm install

# Copy environment file (if needed)
# cp .env.example .env.local
```

## Development (Local Testing)

```bash
# Start development server
npm run dev

# Open http://localhost:3001 in your browser
# Hot-reload enabled — changes appear instantly
```

## Production Build

```bash
# Build optimized production bundle
npm run build

# Start production server
npm start

# Server runs on http://localhost:3001 (configurable)
```

## Static Export (For Static Hosting)

```bash
# Generate static HTML files
npm run export

# Static files are in the out/ directory
# Deploy to GitHub Pages, Netlify, S3, etc.
```

## Docker Deployment

```bash
# Build Docker image
docker build -f Dockerfile -t corvin-marketplace-web:latest .

# Run container
docker run -p 3001:3001 corvin-marketplace-web:latest
```

**Dockerfile** (create this if not present):
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY web .
RUN npm install
RUN npm run build
EXPOSE 3001
ENV NODE_ENV=production
CMD ["npm", "start"]
```

## Environment Variables

Create `.env.local` in the `web/` directory:

```env
# Optional: Base URL for the marketplace
# NEXT_PUBLIC_MARKETPLACE_URL=https://marketplace.corvin.local

# Optional: API timeout (ms)
# NEXT_PUBLIC_API_TIMEOUT=5000

# Optional: Plugin data path (relative to server)
# PLUGIN_DATA_PATH=../../index/plugins.json
```

## Common Tasks

### Add a New Page

```bash
# Create new page in src/pages/about.tsx
# Routes automatically — no configuration needed!
```

### Modify Styling

Edit `src/styles/globals.css` or add Tailwind classes directly to components.

### Update Plugin Data

The marketplace automatically loads plugins from:
```
/home/shumway/projects/Corvin-Marketplace/index/plugins.json
```

If plugins.json changes, restart the dev server.

### Debug in Browser

```bash
# Development mode includes full source maps
# Open DevTools (F12) → Sources tab
# Set breakpoints in TypeScript files
# Changes auto-reload
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 3001 already in use | Change port: `npm run dev -- -p 3002` |
| Plugins not showing | Check `index/plugins.json` exists and is valid JSON |
| Diagrams missing | Verify SVGs exist at `plugins/*/docs/assets/*.svg` |
| Styling broken | Run `npm run build` to regenerate Tailwind CSS |
| Build fails | Delete `.next/` directory and retry: `rm -rf .next && npm run build` |

## Performance Tips

- **Compression**: Enable gzip on your server
- **Caching**: CDN cache static assets (far-future expiry for `/assets/`)
- **Database**: For production, consider caching plugins.json in Redis
- **Monitoring**: Use Vercel Analytics or equivalent for real-world performance

## Security Checklist

- [ ] Set `NEXT_PUBLIC_*` vars only (public content)
- [ ] Never expose API keys in frontend code
- [ ] Enable HTTPS in production
- [ ] Set appropriate CORS headers
- [ ] Validate all user input (search queries)
- [ ] Sanitize markdown rendering (already done with react-markdown)

## Deployment Platforms

### Vercel (Easiest)
```bash
npm install -g vercel
vercel deploy
```

### Netlify
```bash
npm run export
# Drag & drop 'out/' directory to Netlify
```

### AWS Amplify
```bash
amplify init
amplify publish
```

### Self-Hosted (Linux/Docker)
```bash
docker run -d -p 3001:3001 \
  -e NODE_ENV=production \
  corvin-marketplace-web:latest
```

## Monitoring & Logs

```bash
# View production logs
pm2 logs corvin-marketplace

# Monitor performance
npm run build -- --analyze
```

## Next Steps

1. ✅ Install dependencies: `npm install`
2. ✅ Run dev server: `npm run dev`
3. ✅ Open http://localhost:3001
4. ✅ Explore the marketplace
5. ✅ Click a plugin to see full README + diagrams

For advanced topics, see [README.md](./README.md)
