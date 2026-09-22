import Link from 'next/link';
import { Plugin } from '@/lib/plugins';

interface PluginCardProps {
  plugin: Plugin;
}

export default function PluginCard({ plugin }: PluginCardProps) {
  const tierColors: Record<string, { bg: string; text: string }> = {
    production: { bg: 'bg-green-100', text: 'text-green-800' },
    beta: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
    alpha: { bg: 'bg-orange-100', text: 'text-orange-800' },
    contributor: { bg: 'bg-purple-100', text: 'text-purple-800' },
  };

  const tierColor = tierColors[plugin.tier || plugin.origin] || { bg: 'bg-gray-100', text: 'text-gray-800' };

  return (
    <Link href={`/plugins/${plugin.id}`}>
      <div className="h-full bg-white rounded-lg border border-gray-200 hover:shadow-lg hover:border-primary-600 transition-all cursor-pointer p-6 flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <h3 className="text-lg font-bold text-gray-900 leading-tight">{plugin.name}</h3>
            <p className="text-sm text-gray-500 mt-1">{plugin.category}</p>
          </div>
          <span className={`px-2.5 py-1 text-xs font-semibold rounded-full whitespace-nowrap ml-2 ${tierColor.bg} ${tierColor.text}`}>
            {(plugin.tier || plugin.origin).toUpperCase()}
          </span>
        </div>

        {/* Description */}
        <p className="text-gray-600 text-sm mb-4 flex-1 line-clamp-3">{plugin.description}</p>

        {/* Tags */}
        {plugin.tags && plugin.tags.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {plugin.tags.slice(0, 3).map(tag => (
              <span key={tag} className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded">
                {tag}
              </span>
            ))}
            {plugin.tags.length > 3 && (
              <span className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded">
                +{plugin.tags.length - 3}
              </span>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between text-sm border-t border-gray-100 pt-4 mt-auto">
          <div className="text-gray-500">
            <span className="font-mono text-xs">v{plugin.version}</span>
          </div>
          <div className="text-gray-600">
            <span className="font-mono text-xs">{plugin.author}</span>
          </div>
        </div>
      </div>
    </Link>
  );
}
