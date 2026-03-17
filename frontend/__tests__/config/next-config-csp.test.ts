/**
 * Tests for Content Security Policy configuration in next.config.js
 */

// We test the CSP string construction logic directly
describe('next.config.js CSP', () => {
  let nextConfig: any

  beforeEach(() => {
    // Clear module cache to re-evaluate next.config.js
    jest.resetModules()
    // Default to production mode
    // NODE_ENV is read-only in TS strict mode — override via Object.defineProperty
    Object.defineProperty(process.env, 'NODE_ENV', { value: 'production', configurable: true })
    nextConfig = require('../../next.config.js')
  })

  it('should export headers function', () => {
    expect(typeof nextConfig.headers).toBe('function')
  })

  describe('CSP directives', () => {
    let cspHeader: string

    beforeEach(async () => {
      const headerSets = await nextConfig.headers()
      const universalHeaders = headerSets.find(
        (h: any) => h.source === '/(.*)'
      )
      const cspEntry = universalHeaders.headers.find(
        (h: any) => h.key === 'Content-Security-Policy'
      )
      cspHeader = cspEntry.value
    })

    it('should allow Clarity scripts from *.clarity.ms', () => {
      expect(cspHeader).toContain('https://*.clarity.ms')
      // script-src should have the wildcard
      const scriptSrc = cspHeader
        .split(';')
        .find((d: string) => d.trim().startsWith('script-src'))
      expect(scriptSrc).toContain('https://*.clarity.ms')
    })

    it('should allow Clarity images from *.clarity.ms', () => {
      const imgSrc = cspHeader
        .split(';')
        .find((d: string) => d.trim().startsWith('img-src'))
      expect(imgSrc).toContain('https://*.clarity.ms')
    })

    it('should allow OneSignal CDN scripts', () => {
      expect(cspHeader).toContain('https://cdn.onesignal.com')
    })

    it('should set frame-ancestors to none', () => {
      expect(cspHeader).toContain("frame-ancestors 'none'")
    })
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
  })
})
