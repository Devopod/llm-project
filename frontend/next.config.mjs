/** @type {import('next').NextConfig} */
const nextConfig = {
  trailingSlash: true,
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return {
      beforeFiles: [
        {
          source: '/api/:path*/',
          destination: 'http://localhost:8000/api/:path*/',
        },
        {
          source: '/api/:path*',
          destination: 'http://localhost:8000/api/:path*/',
        },
        {
          source: '/ws/:path*',
          destination: 'http://localhost:8000/ws/:path*/',
        },
      ],
    };
  },
};

export default nextConfig;
