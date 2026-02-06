/**
 * Lighthouse CI Configuration
 *
 * Performance targets:
 * - Performance score: 90+
 * - Accessibility score: 90+
 * - Best Practices: 90+
 * - SEO: 90+
 * - First Contentful Paint: <2s
 * - Largest Contentful Paint: <3s
 * - Cumulative Layout Shift: <0.1
 * - Total Blocking Time: <500ms
 */

module.exports = {
  ci: {
    collect: {
      url: [
        'http://localhost:3000/',
        'http://localhost:3000/dashboard',
        'http://localhost:3000/prices',
        'http://localhost:3000/suppliers',
        'http://localhost:3000/optimize',
        'http://localhost:3000/settings',
      ],
      numberOfRuns: 3,
      settings: {
        preset: 'desktop',
        throttling: {
          cpuSlowdownMultiplier: 1,
        },
        skipAudits: ['uses-http2'], // Skip for local testing
      },
    },
    assert: {
      assertions: {
        // Core Web Vitals
        'first-contentful-paint': ['error', { maxNumericValue: 2000 }],
        'largest-contentful-paint': ['error', { maxNumericValue: 3000 }],
        'cumulative-layout-shift': ['error', { maxNumericValue: 0.1 }],
        'total-blocking-time': ['error', { maxNumericValue: 500 }],
        'interactive': ['warn', { maxNumericValue: 4000 }],
        'speed-index': ['warn', { maxNumericValue: 3500 }],

        // Category scores
        'categories:performance': ['error', { minScore: 0.9 }],
        'categories:accessibility': ['error', { minScore: 0.9 }],
        'categories:best-practices': ['error', { minScore: 0.9 }],
        'categories:seo': ['error', { minScore: 0.9 }],

        // Accessibility audits
        'color-contrast': 'error',
        'image-alt': 'error',
        'label': 'error',
        'button-name': 'error',
        'link-name': 'error',
        'document-title': 'error',
        'html-has-lang': 'error',
        'meta-viewport': 'error',
        'tap-targets': 'warn',

        // Best practices
        'errors-in-console': 'warn',
        'no-document-write': 'error',
        'geolocation-on-start': 'error',
        'notification-on-start': 'error',
        'no-vulnerable-libraries': 'error',
        'csp-xss': 'warn',

        // Performance
        'uses-text-compression': 'warn',
        'uses-responsive-images': 'warn',
        'offscreen-images': 'warn',
        'unminified-javascript': 'warn',
        'unminified-css': 'warn',
        'unused-javascript': 'warn',
        'unused-css-rules': 'warn',
        'render-blocking-resources': 'warn',

        // SEO
        'viewport': 'error',
        'robots-txt': 'warn',
        'canonical': 'warn',
        'hreflang': 'off',
        'font-size': 'warn',
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
    server: {
      // For CI environments
      port: 9001,
      storage: '.lighthouseci',
    },
  },
}
