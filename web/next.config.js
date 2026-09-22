/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  typescript: {
    tsconfigPath: './tsconfig.json',
  },
  // Static file serving for plugin documentation
  staticPageGenerationTimeout: 1000,
  // Rewrite plugin paths to serve from parent directory
  async rewrites() {
    return {
      beforeFiles: [
        {
          source: '/plugins/:path*',
          destination: '../../plugins/:path*',
        },
      ],
    };
  },
};

module.exports = nextConfig;
