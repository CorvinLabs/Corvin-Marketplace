import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Plugin } from '@/lib/plugins';

interface PluginDetails extends Plugin {
  readme?: string;
  diagrams?: string[];
}

export default function PluginDetails() {
  const router = useRouter();
  const { id } = router.query;
  const [plugin, setPlugin] = useState<PluginDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id || Array.isArray(id)) return;

    const loadPlugin = async () => {
      try {
        setLoading(true);
        const res = await fetch(`/api/plugins/${id}`);
        if (!res.ok) throw new Error('Plugin not found');

        const data = await res.json();
        setPlugin(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    loadPlugin();
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
          <p className="mt-4 text-gray-600">Loading plugin...</p>
        </div>
      </div>
    );
  }

  if (error || !plugin) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="text-6xl mb-4">❌</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Plugin Not Found</h1>
          <p className="text-gray-600 mb-8">{error || 'The plugin you are looking for does not exist.'}</p>
          <Link href="/" className="px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition">
            Back to Marketplace
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Hero Header */}
      <div className="bg-gradient-to-r from-primary-900 via-primary-800 to-primary-700 text-white">
        <div className="max-w-4xl mx-auto px-4 py-12">
          <Link
            href="/"
            className="inline-flex items-center text-primary-100 hover:text-white mb-6 transition"
          >
            <span className="mr-2">←</span> Back to Marketplace
          </Link>
          <h1 className="text-4xl font-bold mb-3">{plugin.name}</h1>
          <p className="text-primary-100 text-lg mb-6 max-w-2xl">{plugin.description}</p>

          {/* Plugin Meta */}
          <div className="flex flex-wrap gap-4 items-center">
            <span className="px-3 py-1 bg-primary-400/20 text-primary-100 rounded-full text-sm font-medium">
              {(plugin.tier || plugin.origin).toUpperCase()}
            </span>
            <span className="text-primary-100">
              <span className="font-mono">v{plugin.version}</span>
            </span>
            <span className="text-primary-100">By {plugin.author}</span>
            <span className="text-primary-100">{plugin.license}</span>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-4xl mx-auto px-4 py-12">
        {/* Diagrams Section */}
        {plugin.diagrams && plugin.diagrams.length > 0 && (
          <section className="mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-6 border-b-2 border-gray-200 pb-3">
              Architecture & Diagrams
            </h2>
            <div className="space-y-8">
              {plugin.diagrams.map((diagram, idx) => (
                <div key={idx} className="bg-gray-50 rounded-lg border border-gray-200 p-6 overflow-auto">
                  <img
                    src={diagram}
                    alt={`Diagram ${idx + 1}`}
                    className="w-full h-auto"
                  />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* README Content */}
        {plugin.readme && (
          <section className="mb-16">
            <article className="prose prose-lg max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({ children }) => (
                    <h1 className="text-3xl font-bold text-gray-900 mt-8 mb-4 border-b-2 border-gray-200 pb-3">
                      {children}
                    </h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="text-2xl font-bold text-gray-900 mt-6 mb-4 border-b-2 border-gray-200 pb-2">
                      {children}
                    </h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="text-xl font-bold text-gray-900 mt-4 mb-3">{children}</h3>
                  ),
                  p: ({ children }) => <p className="text-gray-700 mb-4 leading-7">{children}</p>,
                  ul: ({ children }) => (
                    <ul className="list-disc list-inside text-gray-700 mb-4 space-y-2">{children}</ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="list-decimal list-inside text-gray-700 mb-4 space-y-2">{children}</ol>
                  ),
                  li: ({ children }) => <li className="text-gray-700">{children}</li>,
                  code: ({ node, inline, children, ...props }: any) =>
                    inline ? (
                      <code
                        className="bg-gray-100 text-red-600 px-2 py-1 rounded font-mono text-sm"
                        {...props}
                      >
                        {children}
                      </code>
                    ) : (
                      <code
                        className="block bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto font-mono text-sm mb-4"
                        {...props}
                      >
                        {children}
                      </code>
                    ),
                  pre: ({ children }) => (
                    <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto mb-4">
                      {children}
                    </pre>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-4 border-primary-600 pl-4 italic text-gray-600 my-4">
                      {children}
                    </blockquote>
                  ),
                  table: ({ children }) => (
                    <div className="overflow-x-auto my-6">
                      <table className="w-full border-collapse border border-gray-300">{children}</table>
                    </div>
                  ),
                  th: ({ children }) => (
                    <th className="border border-gray-300 bg-gray-100 px-4 py-2 text-left font-bold">
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="border border-gray-300 px-4 py-2">{children}</td>
                  ),
                  img: ({ src, alt }) => (
                    <div className="my-6 rounded-lg overflow-hidden border border-gray-200">
                      <img src={src} alt={alt} className="w-full h-auto" />
                    </div>
                  ),
                  a: ({ href, children }) => (
                    <a href={href} className="text-primary-600 hover:text-primary-700 underline">
                      {children}
                    </a>
                  ),
                }}
              >
                {plugin.readme}
              </ReactMarkdown>
            </article>
          </section>
        )}

        {/* Installation */}
        <section className="bg-primary-50 rounded-lg border border-primary-200 p-8 mb-12">
          <h2 className="text-2xl font-bold text-primary-900 mb-4">Installation</h2>
          <p className="text-primary-800 mb-4">Install this plugin using the Corvin CLI:</p>
          <div className="bg-primary-900 rounded-lg p-4 overflow-x-auto">
            <code className="text-primary-50 font-mono">
              corvin marketplace install {plugin.id}
            </code>
          </div>
          <p className="text-primary-700 text-sm mt-4">
            Or add it to your <code className="bg-primary-100 px-2 py-1 rounded">tenant.corvin.yaml</code>:
          </p>
          <div className="bg-primary-900 rounded-lg p-4 overflow-x-auto mt-4">
            <code className="text-primary-50 font-mono text-sm">
              {`plugins:
  - id: ${plugin.id}
    enabled: true`}
            </code>
          </div>
        </section>

        {/* Plugin Info */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-gray-50 rounded-lg p-6 border border-gray-200">
            <h3 className="font-bold text-gray-900 mb-4">Details</h3>
            <dl className="space-y-4 text-sm">
              <div>
                <dt className="text-gray-600 font-semibold">Version</dt>
                <dd className="text-gray-900">{plugin.version}</dd>
              </div>
              <div>
                <dt className="text-gray-600 font-semibold">Category</dt>
                <dd className="text-gray-900 capitalize">{plugin.category}</dd>
              </div>
              <div>
                <dt className="text-gray-600 font-semibold">License</dt>
                <dd className="text-gray-900">{plugin.license}</dd>
              </div>
              <div>
                <dt className="text-gray-600 font-semibold">Boot Layer</dt>
                <dd className="text-gray-900 capitalize">{plugin.boot_layer}</dd>
              </div>
            </dl>
          </div>

          <div className="bg-gray-50 rounded-lg p-6 border border-gray-200">
            <h3 className="font-bold text-gray-900 mb-4">Author</h3>
            <dl className="space-y-4 text-sm">
              <div>
                <dt className="text-gray-600 font-semibold">Author</dt>
                <dd className="text-gray-900">{plugin.author}</dd>
              </div>
              <div>
                <dt className="text-gray-600 font-semibold">Origin</dt>
                <dd className="text-gray-900 capitalize">{plugin.origin}</dd>
              </div>
              {plugin.homepage && (
                <div>
                  <dt className="text-gray-600 font-semibold">Homepage</dt>
                  <dd className="text-gray-900">
                    <a
                      href={plugin.homepage}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 hover:text-primary-700"
                    >
                      Visit
                    </a>
                  </dd>
                </div>
              )}
              {plugin.repository && (
                <div>
                  <dt className="text-gray-600 font-semibold">Repository</dt>
                  <dd className="text-gray-900">
                    <a
                      href={plugin.repository}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 hover:text-primary-700"
                    >
                      GitHub
                    </a>
                  </dd>
                </div>
              )}
            </dl>
          </div>
        </section>
      </div>

      {/* Footer */}
      <div className="bg-gray-900 text-gray-100 py-12 mt-24">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <p className="text-gray-400 mb-6">Questions or feedback about this plugin?</p>
          <div className="flex gap-4 justify-center">
            <Link href="/" className="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition">
              Back to Marketplace
            </Link>
            {plugin.repository && (
              <a
                href={plugin.repository}
                target="_blank"
                rel="noopener noreferrer"
                className="px-6 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-700 transition"
              >
                View on GitHub
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
