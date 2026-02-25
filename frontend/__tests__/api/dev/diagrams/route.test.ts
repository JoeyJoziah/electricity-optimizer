import fs from 'fs'

jest.mock('fs')

/**
 * Minimal Response-like object for testing Next.js API route handlers
 * in the jsdom environment where the Web API Response is not available.
 */
class MockResponse {
  public status: number
  private body: unknown

  constructor(body: unknown, init?: { status?: number }) {
    this.body = body
    this.status = init?.status ?? 200
  }

  async json() {
    return typeof this.body === 'string' ? JSON.parse(this.body) : this.body
  }
}

jest.mock('next/server', () => ({
  NextResponse: {
    json: (body: unknown, init?: { status?: number }) =>
      new MockResponse(body, init),
  },
}))

import { GET, POST } from '@/app/api/dev/diagrams/route'

const env = process.env as { NODE_ENV: string }
const mockedFs = jest.mocked(fs)

describe('GET /api/dev/diagrams', () => {
  const originalNodeEnv = env.NODE_ENV

  beforeEach(() => {
    jest.clearAllMocks()
    env.NODE_ENV = 'development'
  })

  afterEach(() => {
    env.NODE_ENV = originalNodeEnv
  })

  it('returns 404 when NODE_ENV is not development', async () => {
    env.NODE_ENV = 'production'

    const response = await GET()

    expect(response.status).toBe(404)
    const body = await response.json()
    expect(body.error).toBe('Not found')
  })

  it('returns empty list when directory does not exist', async () => {
    mockedFs.existsSync.mockReturnValue(false)

    const response = await GET()

    expect(response.status).toBe(200)
    const body = await response.json()
    expect(body.diagrams).toEqual([])
  })

  it('returns list of .excalidraw files sorted by mtime descending', async () => {
    mockedFs.existsSync.mockReturnValue(true)
    mockedFs.readdirSync.mockReturnValue(
      ['alpha.excalidraw', 'beta.excalidraw', 'readme.md'] as any
    )
    mockedFs.statSync.mockImplementation((filePath: fs.PathLike) => {
      const p = filePath.toString()
      if (p.includes('alpha')) {
        return { mtime: new Date('2026-01-01T00:00:00Z') } as fs.Stats
      }
      if (p.includes('beta')) {
        return { mtime: new Date('2026-02-01T00:00:00Z') } as fs.Stats
      }
      return { mtime: new Date('2026-01-15T00:00:00Z') } as fs.Stats
    })

    const response = await GET()

    expect(response.status).toBe(200)
    const body = await response.json()
    expect(body.diagrams).toHaveLength(2)
    expect(body.diagrams[0].name).toBe('beta')
    expect(body.diagrams[1].name).toBe('alpha')
    expect(body.diagrams[0].updatedAt).toBe('2026-02-01T00:00:00.000Z')
    expect(body.diagrams[1].updatedAt).toBe('2026-01-01T00:00:00.000Z')
  })
})

describe('POST /api/dev/diagrams', () => {
  const originalNodeEnv = env.NODE_ENV

  beforeEach(() => {
    jest.clearAllMocks()
    env.NODE_ENV = 'development'
  })

  afterEach(() => {
    env.NODE_ENV = originalNodeEnv
  })

  function createPostRequest(body: Record<string, unknown>) {
    return {
      json: async () => body,
    } as any
  }

  it('returns 404 when NODE_ENV is not development', async () => {
    env.NODE_ENV = 'production'

    const request = createPostRequest({ name: 'test-diagram' })
    const response = await POST(request)

    expect(response.status).toBe(404)
    const body = await response.json()
    expect(body.error).toBe('Not found')
  })

  it('creates diagram with valid name and returns 201', async () => {
    mockedFs.existsSync.mockReturnValue(false)
    mockedFs.mkdirSync.mockReturnValue(undefined)
    mockedFs.writeFileSync.mockReturnValue(undefined)

    const request = createPostRequest({ name: 'test-diagram' })
    const response = await POST(request)

    expect(response.status).toBe(201)
    const body = await response.json()
    expect(body.name).toBe('test-diagram')
    expect(body.created).toBe(true)
    expect(mockedFs.writeFileSync).toHaveBeenCalledTimes(1)
  })

  it('returns 400 for invalid name with path traversal characters', async () => {
    const request = createPostRequest({ name: '../hack' })
    const response = await POST(request)

    expect(response.status).toBe(400)
    const body = await response.json()
    expect(body.error).toMatch(/Invalid name/)
  })

  it('returns 409 when diagram already exists', async () => {
    mockedFs.existsSync.mockReturnValue(true)

    const request = createPostRequest({ name: 'existing-diagram' })
    const response = await POST(request)

    expect(response.status).toBe(409)
    const body = await response.json()
    expect(body.error).toBe('Diagram already exists')
  })
})
