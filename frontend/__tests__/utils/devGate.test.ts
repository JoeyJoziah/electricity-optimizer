import { isDevMode } from '@/lib/utils/devGate'

const env = process.env as { NODE_ENV: string }

describe('isDevMode', () => {
  const originalNodeEnv = env.NODE_ENV

  afterEach(() => {
    env.NODE_ENV = originalNodeEnv
  })

  it('returns true when NODE_ENV is development', () => {
    env.NODE_ENV = 'development'

    expect(isDevMode()).toBe(true)
  })

  it('returns false when NODE_ENV is production', () => {
    env.NODE_ENV = 'production'

    expect(isDevMode()).toBe(false)
  })

  it('returns false when NODE_ENV is test', () => {
    env.NODE_ENV = 'test'

    expect(isDevMode()).toBe(false)
  })
})
