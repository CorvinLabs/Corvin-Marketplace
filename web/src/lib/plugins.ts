import fs from 'fs';
import path from 'path';

export interface Plugin {
  id: string;
  name: string;
  version: string;
  author: string;
  description: string;
  category: string;
  boot_layer: string;
  tier: string | null;
  origin: string;
  license: string;
  homepage?: string;
  repository?: string;
  tags?: string[];
  readme_path?: string;
  plugin_path?: string;
  diagrams?: string[];
}

// Cache for plugin index
let pluginCache: Plugin[] | null = null;
let pluginMapCache: Map<string, Plugin> | null = null;

export function loadPluginIndex(): Plugin[] {
  if (pluginCache) return pluginCache;

  try {
    // Load from the parent directory's index
    const indexPath = path.join(process.cwd(), '../../index/plugins.json');
    if (!fs.existsSync(indexPath)) {
      console.warn(`Plugin index not found at ${indexPath}`);
      return [];
    }

    const indexData = fs.readFileSync(indexPath, 'utf-8');
    const index = JSON.parse(indexData);

    // Transform index format to our Plugin interface
    pluginCache = (index.plugins || []).map((p: any) => ({
      id: p.id,
      name: p.name,
      version: p.version,
      author: p.author || 'CorvinLabs',
      description: p.description || '',
      category: p.category || 'general',
      boot_layer: p.boot_layer || 'installed',
      tier: p.tier || null,
      origin: p.origin || 'marketplace',
      license: p.license || 'Apache-2.0',
      homepage: p.homepage,
      repository: p.distribution?.source_url,
      tags: p.tags || [],
      readme_path: p.readme_url,
      plugin_path: p.distribution?.source_url,
      diagrams: [],
    }));

    return pluginCache;
  } catch (error) {
    console.error('Failed to load plugin index:', error);
    return [];
  }
}

export function getPluginMap(): Map<string, Plugin> {
  if (pluginMapCache) return pluginMapCache;

  pluginMapCache = new Map();
  const plugins = loadPluginIndex();
  plugins.forEach(p => pluginMapCache!.set(p.id, p));
  return pluginMapCache;
}

export function getPlugin(id: string): Plugin | null {
  const map = getPluginMap();
  return map.get(id) || null;
}

export function searchPlugins(
  query: string = '',
  category: string = 'all'
): Plugin[] {
  const plugins = loadPluginIndex();

  return plugins.filter(p => {
    const matchesQuery =
      query === '' ||
      p.name.toLowerCase().includes(query.toLowerCase()) ||
      p.description.toLowerCase().includes(query.toLowerCase()) ||
      (p.tags || []).some(t => t.toLowerCase().includes(query.toLowerCase()));

    const matchesCategory = category === 'all' || p.category === category;

    return matchesQuery && matchesCategory;
  });
}

export function getCategories(): string[] {
  const plugins = loadPluginIndex();
  const categories = new Set<string>();

  plugins.forEach(p => {
    if (p.category) categories.add(p.category);
  });

  return Array.from(categories).sort();
}

export function loadPluginReadme(pluginPath: string): string {
  try {
    // Construct the path to README.md in the plugin directory
    const readmePath = path.join(process.cwd(), '../../', pluginPath, 'README.md');

    if (!fs.existsSync(readmePath)) {
      return `# Plugin Documentation\n\nREADME not found at ${readmePath}`;
    }

    return fs.readFileSync(readmePath, 'utf-8');
  } catch (error) {
    console.error(`Failed to load README from ${pluginPath}:`, error);
    return '# Error\n\nFailed to load plugin documentation.';
  }
}

export function findPluginDiagrams(pluginPath: string): string[] {
  try {
    const docsPath = path.join(process.cwd(), '../../', pluginPath, 'docs/assets');

    if (!fs.existsSync(docsPath)) {
      return [];
    }

    const files = fs.readdirSync(docsPath);
    return files
      .filter(f => f.endsWith('.svg'))
      .map(f => `/plugins/${pluginPath}/docs/assets/${f}`);
  } catch (error) {
    console.error(`Failed to find diagrams for ${pluginPath}:`, error);
    return [];
  }
}
