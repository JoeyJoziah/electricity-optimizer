// Require NEXT_PUBLIC_APP_URL in production builds (skip during tests)
if (
  process.env.NODE_ENV === 'production' &&
  !process.env.NEXT_PUBLIC_APP_URL &&
  !process.env.JEST_WORKER_ID
) {
  console.error(
    '\x1b[31m[RateShift] NEXT_PUBLIC_APP_URL is not set. ' +
    'This is required in production for canonical URLs, OG tags, and sitemap generation.\x1b[0m'
  )
  // Fail the build so deploys don't proceed with a missing URL
  throw new Error('NEXT_PUBLIC_APP_URL environment variable is required in production')
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // Prevent Next.js from issuing 308 redirects to strip trailing slashes.
  // FastAPI routes use trailing slashes; the 308 ↔ 307 loop is infinite.
  skipTrailingSlashRedirect: true,
  optimizePackageImports: ['date-fns', 'lucide-react', 'recharts', 'better-auth'],

  // Production optimizations
  poweredByHeader: false,
  compress: true,

  // Environment variables
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '/api/v1',
  },

  // Image optimization
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '*.rateshift.app',
      },
    ],
    formats: ['image/avif', 'image/webp'],
  },

  // Security headers (CSP is set per-request in middleware.ts with nonce)
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
        ],
      },
    ]
  },

  // API proxy rewrites — beforeFiles so the rewrite runs before Next.js
  // trailing-slash normalisation (which strips slashes and breaks FastAPI
  // routes that require them, causing infinite 308↔307 redirect loops).
  // Safe because /api/v1/* never collides with Next.js API routes (/api/auth/*).
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'
    return {
      beforeFiles: [
        {
          source: '/api/v1/:path*',
          destination: `${backendUrl}/api/v1/:path*`,
        },
      ],
      afterFiles: [],
      fallback: [],
    }
  },

  // Redirects
  async redirects() {
    return []
  },
}

module.exports = nextConfig
