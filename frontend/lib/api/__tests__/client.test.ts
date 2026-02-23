import { apiClient, ApiClientError } from '@/lib/api/client'

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>

beforeEach(() => {
  mockFetch.mockReset()
})

// ---------------------------------------------------------------------------
// Helper to create mock Response objects
// ---------------------------------------------------------------------------

function mockJsonResponse(body: unknown, status = 200, statusText = 'OK'): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: jest.fn().mockResolvedValue(body),
    headers: new Headers(),
    redirected: false,
    type: 'basic',
    url: '',
    clone: jest.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: jest.fn(),
    blob: jest.fn(),
    formData: jest.fn(),
    text: jest.fn(),
    bytes: jest.fn(),
  } as unknown as Response
}

function mockNonJsonErrorResponse(status: number, statusText: string): Response {
  return {
    ok: false,
    status,
    statusText,
    json: jest.fn().mockRejectedValue(new Error('Not JSON')),
    headers: new Headers(),
    redirected: false,
    type: 'basic',
    url: '',
    clone: jest.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: jest.fn(),
    blob: jest.fn(),
    formData: jest.fn(),
    text: jest.fn(),
    bytes: jest.fn(),
  } as unknown as Response
}

// ---------------------------------------------------------------------------
// apiClient.get
// ---------------------------------------------------------------------------

describe('apiClient.get', () => {
  it('should make a GET request to the correct URL', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ data: 'test' }))

    await apiClient.get('/prices')

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/prices')
  })

  it('should return parsed JSON data on success', async () => {
    const responseData = { prices: [1, 2, 3] }
    mockFetch.mockResolvedValue(mockJsonResponse(responseData))

    const result = await apiClient.get('/prices')
    expect(result).toEqual(responseData)
  })

  it('should append query parameters to the URL', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ data: [] }))

    await apiClient.get('/prices', { region: 'US_CT', period: '24h' })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('region=US_CT')
    expect(calledUrl).toContain('period=24h')
  })

  it('should set Content-Type header to application/json', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({}))

    await apiClient.get('/test')

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('should use GET method', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({}))

    await apiClient.get('/test')

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.method).toBe('GET')
  })

  it('should throw ApiClientError on non-ok response with JSON error body', async () => {
    const errorBody = { detail: 'Not found' }
    mockFetch.mockResolvedValue(mockJsonResponse(errorBody, 404, 'Not Found'))

    await expect(apiClient.get('/missing')).rejects.toThrow(ApiClientError)

    try {
      await apiClient.get('/missing')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiClientError)
      const apiError = error as ApiClientError
      expect(apiError.message).toBe('Not found')
      expect(apiError.status).toBe(404)
      expect(apiError.details).toEqual(errorBody)
    }
  })

  it('should throw ApiClientError with statusText when error body is not JSON', async () => {
    mockFetch.mockResolvedValue(mockNonJsonErrorResponse(500, 'Internal Server Error'))

    try {
      await apiClient.get('/broken')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiClientError)
      const apiError = error as ApiClientError
      expect(apiError.message).toBe('Internal Server Error')
      expect(apiError.status).toBe(500)
    }
  })

  it('should use fallback error message when statusText is also empty', async () => {
    mockFetch.mockResolvedValue(mockNonJsonErrorResponse(500, ''))

    try {
      await apiClient.get('/broken')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiClientError)
      const apiError = error as ApiClientError
      expect(apiError.message).toBe('An error occurred')
    }
  })

  it('should handle GET without params', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ ok: true }))

    const result = await apiClient.get('/health')
    expect(result).toEqual({ ok: true })
  })
})

// ---------------------------------------------------------------------------
// apiClient.post
// ---------------------------------------------------------------------------

describe('apiClient.post', () => {
  it('should make a POST request with JSON body', async () => {
    const payload = { email: 'test@example.com', password: 'secret' }
    mockFetch.mockResolvedValue(mockJsonResponse({ token: 'abc123' }))

    await apiClient.post('/auth/login', payload)

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.method).toBe('POST')
    expect(calledOptions.body).toBe(JSON.stringify(payload))
  })

  it('should return parsed JSON response', async () => {
    const responseData = { token: 'abc123', user: { id: '1' } }
    mockFetch.mockResolvedValue(mockJsonResponse(responseData))

    const result = await apiClient.post('/auth/login', { email: 'a@b.com' })
    expect(result).toEqual(responseData)
  })

  it('should send request without body when data is undefined', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ success: true }))

    await apiClient.post('/trigger')

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.body).toBeUndefined()
  })

  it('should throw ApiClientError on error response', async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse({ message: 'Invalid credentials' }, 401, 'Unauthorized')
    )

    await expect(apiClient.post('/auth/login', {})).rejects.toThrow(ApiClientError)
  })

  it('should set Content-Type to application/json', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({}))

    await apiClient.post('/test', { data: true })

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.headers).toEqual({ 'Content-Type': 'application/json' })
  })
})

// ---------------------------------------------------------------------------
// apiClient.put
// ---------------------------------------------------------------------------

describe('apiClient.put', () => {
  it('should make a PUT request with JSON body', async () => {
    const payload = { name: 'Updated Name' }
    mockFetch.mockResolvedValue(mockJsonResponse({ id: '1', name: 'Updated Name' }))

    await apiClient.put('/users/1', payload)

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.method).toBe('PUT')
    expect(calledOptions.body).toBe(JSON.stringify(payload))
  })

  it('should return parsed JSON response', async () => {
    const responseData = { id: '1', name: 'Updated Name' }
    mockFetch.mockResolvedValue(mockJsonResponse(responseData))

    const result = await apiClient.put('/users/1', { name: 'Updated Name' })
    expect(result).toEqual(responseData)
  })

  it('should handle PUT without body', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ success: true }))

    await apiClient.put('/items/1/activate')

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.body).toBeUndefined()
  })

  it('should throw ApiClientError on error response', async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse({ detail: 'Forbidden' }, 403, 'Forbidden')
    )

    await expect(apiClient.put('/admin/settings', {})).rejects.toThrow(ApiClientError)

    try {
      await apiClient.put('/admin/settings', {})
    } catch (error) {
      const apiError = error as ApiClientError
      expect(apiError.status).toBe(403)
      expect(apiError.message).toBe('Forbidden')
    }
  })
})

// ---------------------------------------------------------------------------
// apiClient.delete
// ---------------------------------------------------------------------------

describe('apiClient.delete', () => {
  it('should make a DELETE request', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ deleted: true }))

    await apiClient.delete('/users/1')

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/users/1')
    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.method).toBe('DELETE')
  })

  it('should return parsed JSON response', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ deleted: true }))

    const result = await apiClient.delete('/users/1')
    expect(result).toEqual({ deleted: true })
  })

  it('should not send a body', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ deleted: true }))

    await apiClient.delete('/users/1')

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.body).toBeUndefined()
  })

  it('should throw ApiClientError on error response', async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse({ detail: 'Not found' }, 404, 'Not Found')
    )

    await expect(apiClient.delete('/users/999')).rejects.toThrow(ApiClientError)
  })

  it('should set Content-Type header', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({}))

    await apiClient.delete('/test')

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.headers).toEqual({ 'Content-Type': 'application/json' })
  })
})

// ---------------------------------------------------------------------------
// ApiClientError class
// ---------------------------------------------------------------------------

describe('ApiClientError', () => {
  it('should be an instance of Error', () => {
    const error = new ApiClientError({ message: 'test', status: 400 })
    expect(error).toBeInstanceOf(Error)
    expect(error).toBeInstanceOf(ApiClientError)
  })

  it('should store message, status, and details', () => {
    const error = new ApiClientError({
      message: 'Bad request',
      status: 400,
      details: { field: 'email', issue: 'required' },
    })
    expect(error.message).toBe('Bad request')
    expect(error.status).toBe(400)
    expect(error.details).toEqual({ field: 'email', issue: 'required' })
  })

  it('should have name set to ApiClientError', () => {
    const error = new ApiClientError({ message: 'test', status: 500 })
    expect(error.name).toBe('ApiClientError')
  })

  it('should handle missing details', () => {
    const error = new ApiClientError({ message: 'test', status: 500 })
    expect(error.details).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Error handling edge cases
// ---------------------------------------------------------------------------

describe('error handling edge cases', () => {
  it('should prefer detail field over message field in error response', async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse({ detail: 'Detail error', message: 'Message error' }, 400)
    )

    try {
      await apiClient.get('/test')
    } catch (error) {
      const apiError = error as ApiClientError
      expect(apiError.message).toBe('Detail error')
    }
  })

  it('should fall back to message field when detail is absent', async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse({ message: 'Message error' }, 400)
    )

    try {
      await apiClient.get('/test')
    } catch (error) {
      const apiError = error as ApiClientError
      expect(apiError.message).toBe('Message error')
    }
  })

  it('should use default message when error body has neither detail nor message', async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse({ code: 'ERR_UNKNOWN' }, 400)
    )

    try {
      await apiClient.get('/test')
    } catch (error) {
      const apiError = error as ApiClientError
      expect(apiError.message).toBe('An error occurred')
    }
  })

  it('should store the full error body as details', async () => {
    const errorBody = { detail: 'Validation failed', errors: [{ field: 'email' }] }
    mockFetch.mockResolvedValue(mockJsonResponse(errorBody, 422))

    try {
      await apiClient.get('/test')
    } catch (error) {
      const apiError = error as ApiClientError
      expect(apiError.details).toEqual(errorBody)
    }
  })
})
