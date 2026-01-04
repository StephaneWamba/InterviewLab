import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* Ignore TypeScript errors during build */
  typescript: {
    ignoreBuildErrors: true,
  },

  /* Performance optimizations */
  compress: true,
  poweredByHeader: false,
  
  /* Image optimization */
  images: {
    formats: ['image/avif', 'image/webp'],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920, 2048, 3840],
    imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
  },

  /* Experimental features for better performance */
  experimental: {
    optimizePackageImports: ['lucide-react', '@radix-ui/react-icons'],
  },

  /* Server components external packages - prevents bundling on server */
  serverExternalPackages: ['livekit-client', '@livekit/components-react'],

  /* Headers for security and performance */
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on'
          },
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          {
            key: 'Referrer-Policy',
            value: 'origin-when-cross-origin'
          }
        ],
      },
    ];
  },
};

export default nextConfig;
