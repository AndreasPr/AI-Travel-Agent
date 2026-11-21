/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    const origin = process.env.API_PROXY_URL;
    if (!origin) return [];
    const parsed = new URL(origin);
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.pathname !== '/') throw new Error('API_PROXY_URL must be an HTTPS origin');
    return [{ source: '/api/:path*', destination: `${parsed.origin}/api/:path*` }];
  },
};

export default nextConfig;
