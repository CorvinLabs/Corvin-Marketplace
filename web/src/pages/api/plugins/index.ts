import type { NextApiRequest, NextApiResponse } from 'next';
import { searchPlugins, getCategories } from '@/lib/plugins';

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  const { q = '', category = 'all' } = req.query;

  try {
    const query = Array.isArray(q) ? q[0] : q;
    const cat = Array.isArray(category) ? category[0] : category;

    const plugins = searchPlugins(query, cat);
    const categories = getCategories();

    res.status(200).json({
      success: true,
      count: plugins.length,
      plugins,
      categories,
      query,
      category: cat,
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to load plugins',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
