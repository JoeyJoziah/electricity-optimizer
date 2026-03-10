/**
 * Tests for the centralized environment variable configuration.
 *
 * Because env.ts reads process.env at module evaluation time,
 * we use jest.resetModules() + dynamic import() to re-evaluate
 * the module with different env var values for each test.
 */

// We replace process.env wholesale in these tests, which requires
// bypassing the read-only NODE_ENV typing from Next.js.
const env = process.env as Record<string, string | undefined>
const ORIGINAL_ENV = { ...env }

beforeEach(() => {
  jest.resetModules()
  // Restore a fresh copy so tests are isolated
  for (const key of Object.keys(env)) {
    delete env[key]
  }
  Object.assign(env, ORIGINAL_ENV)
})

afterAll(() => {
  for (const key of Object.keys(env)) {
    delete env[key]
  }
  Object.assign(env, ORIGINAL_ENV)
})

describe('lib/config/env', () => {
  describe('API_URL', () => {
    it('uses NEXT_PUBLIC_API_URL when set', async () => {
      env.NEXT_PUBLIC_API_URL = 'https://api.example.com/api/v1'
      const { API_URL } = await import('@/lib/config/env')
      expect(API_URL).toBe('https://api.example.com/api/v1')
    })

    it('falls back to relative /api/v1 in development', async () => {
      delete env.NEXT_PUBLIC_API_URL
      env.NODE_ENV = 'development'
      const { API_URL } = await import('@/lib/config/env')
      expect(API_URL).toBe('/api/v1')
    })
  })

  describe('API_ORIGIN', () => {
    it('strips the path from API_URL', async () => {
      env.NEXT_PUBLIC_API_URL = 'https://api.example.com/api/v1'
      const { API_ORIGIN } = await import('@/lib/config/env')
      expect(API_ORIGIN).toBe('https://api.example.com')
    })

    it('preserves the port when present', async () => {
      env.NEXT_PUBLIC_API_URL = 'http://localhost:8000/api/v1'
      const { API_ORIGIN } = await import('@/lib/config/env')
      expect(API_ORIGIN).toBe('http://localhost:8000')
    })

    it('returns empty string for relative API_URL (same-origin proxy)', async () => {
      delete env.NEXT_PUBLIC_API_URL
      env.NODE_ENV = 'development'
      const { API_ORIGIN } = await import('@/lib/config/env')
      expect(API_ORIGIN).toBe('')
    })
  })

  describe('APP_URL', () => {
    it('uses NEXT_PUBLIC_APP_URL when set', async () => {
      env.NEXT_PUBLIC_APP_URL = 'https://app.example.com'
      const { APP_URL } = await import('@/lib/config/env')
      expect(APP_URL).toBe('https://app.example.com')
    })

    it('falls back to localhost:3000 in development', async () => {
      delete env.NEXT_PUBLIC_APP_URL
      env.NODE_ENV = 'development'
      const { APP_URL } = await import('@/lib/config/env')
      expect(APP_URL).toBe('http://localhost:3000')
    })
  })

  describe('SITE_URL', () => {
    it('uses NEXT_PUBLIC_SITE_URL when set', async () => {
      env.NEXT_PUBLIC_SITE_URL = 'https://www.my-site.com'
      const { SITE_URL } = await import('@/lib/config/env')
      expect(SITE_URL).toBe('https://www.my-site.com')
    })

    it('falls back to vercel app URL when not set', async () => {
      delete env.NEXT_PUBLIC_SITE_URL
      env.NODE_ENV = 'development'
      const { SITE_URL } = await import('@/lib/config/env')
      expect(SITE_URL).toBe('https://rateshift.app')
    })
  })

  describe('production validation', () => {
    it('uses /api/v1 fallback in production when API_URL is missing', async () => {
      delete env.NEXT_PUBLIC_API_URL
      env.NODE_ENV = 'production'

      const { API_URL } = await import('@/lib/config/env')
      expect(API_URL).toBe('/api/v1')
    })

    it('does NOT throw for optional vars (APP_URL) in production', async () => {
      env.NEXT_PUBLIC_API_URL = 'https://api.example.com/api/v1'
      delete env.NEXT_PUBLIC_APP_URL
      delete env.NEXT_PUBLIC_SITE_URL
      env.NODE_ENV = 'production'

      const { APP_URL, SITE_URL } = await import('@/lib/config/env')
      // Falls back to defaults without throwing
      expect(APP_URL).toBe('http://localhost:3000')
      expect(SITE_URL).toBe('https://rateshift.app')
    })
  })

  describe('environment flags', () => {
    it('sets IS_PRODUCTION correctly', async () => {
      env.NODE_ENV = 'production'
      env.NEXT_PUBLIC_API_URL = 'https://api.example.com/api/v1'
      const { IS_PRODUCTION, IS_DEV, IS_TEST } = await import('@/lib/config/env')
      expect(IS_PRODUCTION).toBe(true)
      expect(IS_DEV).toBe(false)
      expect(IS_TEST).toBe(false)
    })

    it('sets IS_TEST correctly', async () => {
      env.NODE_ENV = 'test'
      const { IS_PRODUCTION, IS_DEV, IS_TEST } = await import('@/lib/config/env')
      expect(IS_PRODUCTION).toBe(false)
      expect(IS_DEV).toBe(false)
      expect(IS_TEST).toBe(true)
    })

    it('sets IS_DEV correctly', async () => {
      env.NODE_ENV = 'development'
      const { IS_PRODUCTION, IS_DEV, IS_TEST } = await import('@/lib/config/env')
      expect(IS_PRODUCTION).toBe(false)
      expect(IS_DEV).toBe(true)
      expect(IS_TEST).toBe(false)
    })
  })
})
