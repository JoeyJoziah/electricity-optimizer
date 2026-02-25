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

import { GET, PUT } from '@/app/api/dev/diagrams/[name]/route'

const env = process.env as { NODE_ENV: string }
const mockedFs = jest.mocked(fs)

describe('GET /api/dev/diagrams/[name]', () => {
  const originalNodeEnv = env.NODE_ENV

  beforeEach(() => {
    jest.clearAllMocks()
    env.NODE_ENV = 'development'
  })

  afterEach(() => {
    env.NODE_ENV = originalNodeEnv
  })

  function createRequest() {
    return { method: 'GET' } as any
  }

  it('returns 404 when NODE_ENV is not development', async () => {
    env.NODE_ENV = 'production'

    const response = await GET(createRequest(), { params: { name: 'test' } })

    expect(response.status).toBe(404)
    const body = await response.json()
    expect(body.error).toBe('Not found')
  })

  it('returns diagram data for valid name', async () => {
    const diagramData = {
      type: 'excalidraw',
      version: 2,
      elements: [{ id: '1', type: 'rectangle' }],
    }

    mockedFs.existsSync.mockReturnValue(true)
    mockedFs.readFileSync.mockReturnValue(JSON.stringify(diagramData))

    const response = await GET(createRequest(), { params: { name: 'my-diagram' } })

    expect(response.status).toBe(200)
    const body = await response.json()
    expect(body.name).toBe('my-diagram')
    expect(body.data).toEqual(diagramData)
  })

  it('returns 400 for path traversal attempt', async () => {
    const response = await GET(createRequest(), { params: { name: '../etc/passwd' } })

    expect(response.status).toBe(400)
    const body = await response.json()
    expect(body.error).toBe('Invalid diagram name')
  })

  it('returns 404 for non-existent diagram', async () => {
    mockedFs.existsSync.mockReturnValue(false)

    const response = await GET(createRequest(), { params: { name: 'missing-diagram' } })

    expect(response.status).toBe(404)
    const body = await response.json()
    expect(body.error).toBe('Diagram not found')
  })
})

describe('PUT /api/dev/diagrams/[name]', () => {
  const originalNodeEnv = env.NODE_ENV

  beforeEach(() => {
    jest.clearAllMocks()
    env.NODE_ENV = 'development'
  })

  afterEach(() => {
    env.NODE_ENV = originalNodeEnv
  })

  function createPutRequest(body: Record<string, unknown>) {
    return {
      json: async () => body,
    } as any
  }

  it('returns 404 when NODE_ENV is not development', async () => {
    env.NODE_ENV = 'production'

    const request = createPutRequest({ data: { elements: [] } })
    const response = await PUT(request, { params: { name: 'test' } })

    expect(response.status).toBe(404)
    const body = await response.json()
    expect(body.error).toBe('Not found')
  })

  it('saves diagram data successfully', async () => {
    const updatedData = {
      type: 'excalidraw',
      version: 2,
      elements: [{ id: '1', type: 'rectangle' }],
    }

    mockedFs.existsSync.mockReturnValue(true)
    mockedFs.writeFileSync.mockReturnValue(undefined)

    const request = createPutRequest({ data: updatedData })
    const response = await PUT(request, { params: { name: 'my-diagram' } })

    expect(response.status).toBe(200)
    const body = await response.json()
    expect(body.name).toBe('my-diagram')
    expect(body.saved).toBe(true)
    expect(mockedFs.writeFileSync).toHaveBeenCalledTimes(1)
    expect(mockedFs.writeFileSync).toHaveBeenCalledWith(
      expect.stringContaining('my-diagram.excalidraw'),
      JSON.stringify(updatedData, null, 2)
    )
  })

  it('returns 400 for invalid data when data field is missing', async () => {
    mockedFs.existsSync.mockReturnValue(true)

    const request = createPutRequest({ notData: 'something' })
    const response = await PUT(request, { params: { name: 'my-diagram' } })

    expect(response.status).toBe(400)
    const body = await response.json()
    expect(body.error).toBe('Invalid diagram data')
  })
})
