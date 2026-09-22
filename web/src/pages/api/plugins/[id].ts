import type { NextApiRequest, NextApiResponse } from 'next';
import { getPlugin, loadPluginReadme, findPluginDiagrams } from '@/lib/plugins';

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  const { id } = req.query;

  if (!id || Array.isArray(id)) {
    res.status(400).json({ error: 'Invalid plugin ID' });
    return;
  }

  try {
    const plugin = getPlugin(id);

    if (!plugin) {
      res.status(404).json({ error: 'Plugin not found' });
      return;
    }

    // Try to load README and diagrams if we have a plugin path
    let readme = '';
    let diagrams: string[] = [];

    if (plugin.plugin_path) {
      try {
        readme = loadPluginReadme(plugin.plugin_path);
        diagrams = findPluginDiagrams(plugin.plugin_path);
      } catch (error) {
        console.error(`Failed to load plugin assets for ${id}:`, error);
      }
    }

    res.status(200).json({
      ...plugin,
      readme,
      diagrams,
    });
  } catch (error) {
    res.status(500).json({
      error: 'Failed to load plugin details',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
