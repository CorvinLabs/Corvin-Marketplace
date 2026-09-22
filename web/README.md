# Corvin Marketplace Web UI

A Next.js-based web interface for discovering and browsing Corvin plugins in the Corvin Marketplace.

## Features

- **Plugin Discovery**: Browse all plugins in the Corvin Marketplace
- **Search & Filter**: Search by name, description, or tags; filter by category
- **Plugin Details**: View full README.md with syntax highlighting
- **Architecture Diagrams**: Embedded SVG diagrams from plugin documentation
- **Professional UI**: Responsive design with Tailwind CSS
- **Static Generation**: Optimized for fast loading and deployment

## Setup

### Prerequisites

- Node.js 18+ (LTS recommended)
- npm or yarn

### Installation

```bash
cd web
npm install
```

### Development

```bash
npm run dev
```

The marketplace will be available at `http://localhost:3001`.

### Build for Production

```bash
npm run build
npm start
```

### Export as Static Site

```bash
npm run export
```

This generates a static HTML export in the `out/` directory that can be deployed to any static hosting service.

## Project Structure

```
web/
├── src/
│   ├── pages/
│   │   ├── index.tsx          # Marketplace index page
│   │   ├── plugins/[id].tsx   # Plugin details page
│   │   ├── api/
│   │   │   └── plugins/
│   │   │       ├── index.ts   # List plugins API
│   │   │       └── [id].ts    # Plugin details API
│   │   ├── _app.tsx           # Next.js app wrapper
│   │   └── 404.tsx            # 404 error page
│   ├── components/
│   │   └── PluginCard.tsx     # Reusable plugin card component
│   ├── lib/
│   │   └── plugins.ts         # Plugin loading utilities
│   └── styles/
│       └── globals.css        # Global styles & Tailwind
├── package.json
├── next.config.js
├── tsconfig.json
└── tailwind.config.ts
```

## API Endpoints

### Get Plugins List
```
GET /api/plugins?q=<query>&category=<category>
```

**Query Parameters:**
- `q` (optional): Search query
- `category` (optional): Filter by category (default: 'all')

**Response:**
```json
{
  "success": true,
  "count": 10,
  "plugins": [...],
  "categories": ["integration", "security", ...]
}
```

### Get Plugin Details
```
GET /api/plugins/[id]
```

**Response:**
```json
{
  "id": "plugin:...",
  "name": "Plugin Name",
  "version": "1.0.0",
  "description": "...",
  "readme": "# README content...",
  "diagrams": ["/plugins/...", "..."]
}
```

## Deployment

### Vercel (Recommended)

```bash
vercel deploy
```

### Docker

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY web .
RUN npm install
RUN npm run build
EXPOSE 3001
CMD ["npm", "start"]
```

Build and run:
```bash
docker build -t corvin-marketplace .
docker run -p 3001:3001 corvin-marketplace
```

### Static HTML Export

```bash
npm run export
# Static files are in the out/ directory
```

## Development Notes

- **Plugin Data**: Loads from `/home/shumway/projects/Corvin-Marketplace/index/plugins.json`
- **README Files**: Automatically located in plugin directories
- **SVG Diagrams**: Discovered from `docs/assets/*.svg` in plugin directories
- **Styling**: Uses Tailwind CSS with custom color scheme (primary-600 blue)
- **Markdown**: Renders with syntax highlighting and GitHub Flavored Markdown support

## Troubleshooting

### Plugins not loading
- Verify `index/plugins.json` exists and is valid JSON
- Check the plugin paths in the index file
- Ensure README.md files exist in plugin directories

### Diagrams not showing
- Verify SVG files exist in `plugins/<category>/<name>/docs/assets/`
- Check browser console for 404 errors
- Ensure SVG files are valid XML

### Styling issues
- Run `npm run build` to regenerate Tailwind CSS
- Clear Next.js cache: `rm -rf .next`
- Check for CSS conflicts in `src/styles/globals.css`

## License

Apache-2.0 - See LICENSE in the parent directory

## Contributing

See CONTRIBUTING.md in the parent directory for guidelines.
