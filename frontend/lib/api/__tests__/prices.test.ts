import {
  getCurrentPrices,
  getPriceHistory,
  getPriceForecast,
  getOptimalPeriods,
} from '@/lib/api/prices'
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
// getCurrentPrices
// ---------------------------------------------------------------------------

describe('getCurrentPrices', () => {
  it('calls correct endpoint', async () => {
    const responseData = {
      prices: [{ region: 'US_CT', price: 0.25, timestamp: '2026-02-24T12:00:00Z' }],
    }
    mockFetch.mockResolvedValue(mockJsonResponse(responseData))

    await getCurrentPrices()

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/prices/current')
  })

  it('passes region parameter', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ prices: [] }))

    await getCurrentPrices('us_ny')

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('region=us_ny')
  })
})

// ---------------------------------------------------------------------------
// getPriceHistory
// ---------------------------------------------------------------------------

describe('getPriceHistory', () => {
  it('includes hours parameter', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ prices: [] }))

    await getPriceHistory('us_ct', 48)

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/prices/history')
    expect(calledUrl).toContain('hours=48')
    expect(calledUrl).toContain('region=us_ct')
  })
})

// ---------------------------------------------------------------------------
// getPriceForecast
// ---------------------------------------------------------------------------

describe('getPriceForecast', () => {
  it('calls forecast endpoint', async () => {
    const forecastData = {
      forecast: [{ hour: 1, price: 0.23, confidence: [0.21, 0.25] }],
    }
    mockFetch.mockResolvedValue(mockJsonResponse(forecastData))

    const result = await getPriceForecast('us_ct', 24)

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/prices/forecast')
    expect(calledUrl).toContain('region=us_ct')
    expect(calledUrl).toContain('hours=24')
    expect(result).toEqual(forecastData)
  })
})

// ---------------------------------------------------------------------------
// getOptimalPeriods
// ---------------------------------------------------------------------------

describe('getOptimalPeriods', () => {
  it('calls optimal-periods endpoint', async () => {
    const periodsData = {
      periods: [
        { start: '2026-02-24T02:00:00Z', end: '2026-02-24T05:00:00Z', avgPrice: 0.15 },
      ],
    }
    mockFetch.mockResolvedValue(mockJsonResponse(periodsData))

    const result = await getOptimalPeriods('us_ct', 24)

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/prices/optimal-periods')
    expect(calledUrl).toContain('region=us_ct')
    expect(calledUrl).toContain('hours=24')
    expect(result).toEqual(periodsData)
  })
})

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe('error handling', () => {
  it('handles 401 unauthorized response', async () => {
    // Mock window.location for 401 redirect behavior
    const originalLocation = window.location
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, href: '' },
    })

    mockFetch.mockResolvedValue(
      mockJsonResponse({ detail: 'Unauthorized' }, 401, 'Unauthorized')
    )

    await expect(getCurrentPrices()).rejects.toThrow(ApiClientError)

    try {
      await getCurrentPrices()
    } catch (error) {
      const apiError = error as ApiClientError
      expect(apiError.status).toBe(401)
    }

    // Restore
    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    })
  })

  it('handles 500 server error', async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse({ detail: 'Internal Server Error' }, 500, 'Internal Server Error')
    )

    // With retry, the client will try MAX_RETRIES+1 times for 500 errors
    await expect(getCurrentPrices()).rejects.toThrow(ApiClientError)

    try {
      await getCurrentPrices()
    } catch (error) {
      const apiError = error as ApiClientError
      expect(apiError.status).toBe(500)
      expect(apiError.message).toBe('Internal Server Error')
    }
  })

  it('handles network timeout', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'))

    // The client retries on TypeError (network errors), so it will
    // eventually throw after exhausting retries
    await expect(getCurrentPrices()).rejects.toThrow(TypeError)
  })
})
