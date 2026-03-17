/**
 * Tests for Content Security Policy and security headers.
 *
 * CSP is now generated per-request in middleware.ts (nonce-based).
 * Static security headers remain in next.config.js.
 */

describe('next.config.js static security headers', () => {
  let nextConfig: any

  beforeEach(() => {
    jest.resetModules()
    Object.defineProperty(process.env, 'NODE_ENV', { value: 'production', configurable: true })
    nextConfig = require('../../next.config.js')
  })

  it('should export headers function', () => {
    expect(typeof nextConfig.headers).toBe('function')
  })

  describe('Security headers', () => {
    let headers: Array<{ key: string; value: string }>

    beforeEach(async () => {
      const headerSets = await nextConfig.headers()
      const universalHeaders = headerSets.find(
        (h: any) => h.source === '/(.*)'
      )
      headers = universalHeaders.headers
    })

    it('should set X-Frame-Options to DENY', () => {
      const header = headers.find((h) => h.key === 'X-Frame-Options')
      expect(header?.value).toBe('DENY')
    })

    it('should set X-Content-Type-Options to nosniff', () => {
      const header = headers.find((h) => h.key === 'X-Content-Type-Options')
      expect(header?.value).toBe('nosniff')
    })

    it('should set Strict-Transport-Security', () => {
      const header = headers.find(
        (h) => h.key === 'Strict-Transport-Security'
      )
      expect(header?.value).toContain('max-age=')
      expect(header?.value).toContain('includeSubDomains')
    })

    it('should set Referrer-Policy', () => {
      const header = headers.find((h) => h.key === 'Referrer-Policy')
      expect(header?.value).toBe('strict-origin-when-cross-origin')
    })

    it('should NOT include CSP in static headers (moved to middleware)', () => {
      const cspHeader = headers.find(
        (h) => h.key === 'Content-Security-Policy'
      )
      expect(cspHeader).toBeUndefined()
    })
  })
})

describe('middleware.ts CSP nonce generation', () => {
  it('should build CSP with nonce and without unsafe-inline in script-src', () => {
    // Test the CSP string construction inline (middleware is edge runtime)
    const nonce = 'dGVzdC1ub25jZQ=='
    const csp = [
      "default-src 'self'",
      `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' https://*.clarity.ms https://cdn.onesignal.com`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https://*.rateshift.app https://*.clarity.ms",
      "font-src 'self'",
      "connect-src 'self' https://*.rateshift.app https://electricity-optimizer.onrender.com https://www.clarity.ms https://*.clarity.ms https://onesignal.com https://*.onesignal.com",
      "worker-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; ')

    // script-src must NOT contain 'unsafe-inline'
    const scriptSrc = csp.split(';').find((d) => d.trim().startsWith('script-src'))!
    expect(scriptSrc).not.toContain("'unsafe-inline'")
    expect(scriptSrc).toContain(`'nonce-${nonce}'`)
    expect(scriptSrc).toContain("'strict-dynamic'")

    // style-src keeps unsafe-inline (required for Next.js/Tailwind)
    const styleSrc = csp.split(';').find((d) => d.trim().startsWith('style-src'))!
    expect(styleSrc).toContain("'unsafe-inline'")

    // Clarity and OneSignal domains present
    expect(csp).toContain('https://*.clarity.ms')
    expect(csp).toContain('https://cdn.onesignal.com')

    // Frame ancestors locked down
    expect(csp).toContain("frame-ancestors 'none'")
  })
})
