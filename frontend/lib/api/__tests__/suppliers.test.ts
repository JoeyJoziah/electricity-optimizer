import {
  getSuppliers,
  getSupplier,
  compareSuppliers,
} from '@/lib/api/suppliers'
import { ApiClientError } from '@/lib/api/client'
import '@testing-library/jest-dom'

// ---------------------------------------------------------------------------
// Setup - mock fetch (already globally mocked in jest.setup.js)
// ---------------------------------------------------------------------------

const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>

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

beforeEach(() => {
  mockFetch.mockReset()
})

// ---------------------------------------------------------------------------
// getSuppliers
// ---------------------------------------------------------------------------

describe('getSuppliers', () => {
  it('calls correct endpoint', async () => {
    const responseData = {
      suppliers: [
        { id: '1', name: 'Eversource Energy', avgPricePerKwh: 0.25 },
      ],
    }
    mockFetch.mockResolvedValue(mockJsonResponse(responseData))

    const result = await getSuppliers()

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/suppliers')
    expect(result).toEqual(responseData)
  })

  it('passes region filter', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ suppliers: [] }))

    await getSuppliers('us_ny')

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('region=us_ny')
  })
})

// ---------------------------------------------------------------------------
// getSupplier (by ID)
// ---------------------------------------------------------------------------

describe('getSupplierDetails', () => {
  it('fetches by ID', async () => {
    const supplier = {
      id: 'supplier_001',
      name: 'Eversource Energy',
      avgPricePerKwh: 0.25,
      rating: 4.5,
    }
    mockFetch.mockResolvedValue(mockJsonResponse(supplier))

    const result = await getSupplier('supplier_001')

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/suppliers/supplier_001')
    expect(result).toEqual(supplier)
  })
})

// ---------------------------------------------------------------------------
// compareSuppliers
// ---------------------------------------------------------------------------

describe('compareSuppliers', () => {
  it('calls compare endpoint', async () => {
    const comparisonData = {
      comparisons: [
        { id: '1', name: 'Eversource', estimatedAnnualCost: 1200 },
        { id: '2', name: 'NextEra', estimatedAnnualCost: 1050 },
      ],
    }
    mockFetch.mockResolvedValue(mockJsonResponse(comparisonData))

    const result = await compareSuppliers(['1', '2'], 10500)

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/suppliers/compare')

    // Verify it was a POST request with the correct body
    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.method).toBe('POST')
    expect(JSON.parse(calledOptions.body as string)).toEqual({
      supplierIds: ['1', '2'],
      annualUsage: 10500,
    })

    expect(result).toEqual(comparisonData)
  })
})

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe('error handling', () => {
  it('handles 401 unauthorized', async () => {
    const originalLocation = window.location
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, href: '' },
    })

    mockFetch.mockResolvedValue(
      mockJsonResponse({ detail: 'Not authenticated' }, 401, 'Unauthorized')
    )

    await expect(getSuppliers()).rejects.toThrow(ApiClientError)

    try {
      await getSuppliers()
    } catch (error) {
      const apiError = error as ApiClientError
      expect(apiError.status).toBe(401)
    }

    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    })
  })

  it('handles empty response', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ suppliers: [] }))

    const result = await getSuppliers()

    expect(result).toEqual({ suppliers: [] })
    expect(result.suppliers).toHaveLength(0)
  })

  it('handles network error', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'))

    // The client retries on network errors (TypeError), eventually throws
    await expect(getSuppliers()).rejects.toThrow(TypeError)
  })

  it('request includes credentials for auth', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ suppliers: [] }))

    await getSuppliers()

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit
    expect(calledOptions.credentials).toBe('include')
    expect(calledOptions.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' })
    )
  })
})
