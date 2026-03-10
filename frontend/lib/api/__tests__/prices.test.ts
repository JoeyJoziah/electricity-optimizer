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
    // Backend shape: prices[] contains ApiPriceResponse with current_price (Decimal string)
    const responseData = {
      prices: [
        {
          ticker: 'ELEC-US_CT',
          current_price: '0.2500',
          currency: 'USD',
          region: 'us_ct',
          supplier: 'Eversource Energy',
          updated_at: '2026-02-24T12:00:00Z',
          is_peak: false,
          carbon_intensity: null,
          price_change_24h: null,
        },
      ],
      region: 'us_ct',
      timestamp: '2026-02-24T12:00:00Z',
      source: 'live',
      price: null,
    }
    mockFetch.mockResolvedValue(mockJsonResponse(responseData))

    await getCurrentPrices({ region: 'us_ct' })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/prices/current')
  })

  it('passes region parameter', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ prices: [], price: null, region: 'us_ny', timestamp: '2026-02-24T12:00:00Z', source: null }))

    await getCurrentPrices({ region: 'us_ny' })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('region=us_ny')
  })

  it('passes optional supplier parameter', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ price: null, prices: null, region: 'us_ct', timestamp: '2026-02-24T12:00:00Z', source: null }))

    await getCurrentPrices({ region: 'us_ct', supplier: 'Eversource Energy' })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('supplier=Eversource+Energy')
  })
})

// ---------------------------------------------------------------------------
// getPriceHistory
// ---------------------------------------------------------------------------

describe('getPriceHistory', () => {
  it('includes days parameter', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({
      region: 'us_ct',
      supplier: null,
      start_date: '2026-02-22T12:00:00Z',
      end_date: '2026-02-24T12:00:00Z',
      prices: [],
      average_price: null,
      min_price: null,
      max_price: null,
      source: 'live',
      total: 0,
      page: 1,
      page_size: 24,
      pages: 1,
    }))

    await getPriceHistory({ region: 'us_ct', days: 2 })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/v1/prices/history')
    expect(calledUrl).toContain('days=2')
    expect(calledUrl).toContain('region=us_ct')
  })

  it('includes page parameters', async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({
      region: 'us_ct',
      supplier: null,
      start_date: '2026-02-22T12:00:00Z',
      end_date: '2026-02-24T12:00:00Z',
      prices: [],
      average_price: null,
      min_price: null,
      max_price: null,
      source: 'live',
      total: 0,
      page: 2,
      page_size: 10,
      pages: 1,
    }))

    await getPriceHistory({ region: 'us_ct', page: 2, pageSize: 10 })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('page=2')
    expect(calledUrl).toContain('page_size=10')
  })
})

// ---------------------------------------------------------------------------
// getPriceForecast
// ---------------------------------------------------------------------------

describe('getPriceForecast', () => {
  it('calls forecast endpoint', async () => {
    const forecastData = {
      region: 'us_ct',
      forecast: {
        id: 'abc',
        region: 'us_ct',
        generated_at: '2026-02-24T12:00:00Z',
        horizon_hours: 24,
        prices: [],
        confidence: 0.85,
        model_version: 'v1',
        source_api: null,
      },
      generated_at: '2026-02-24T12:00:00Z',
      horizon_hours: 24,
      confidence: 0.85,
      source: 'live',
    }
    mockFetch.mockResolvedValue(mockJsonResponse(forecastData))

    const result = await getPriceForecast({ region: 'us_ct', hours: 24 })

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

    await expect(getCurrentPrices({ region: 'us_ct' })).rejects.toThrow(ApiClientError)

    try {
      await getCurrentPrices({ region: 'us_ct' })
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
    await expect(getCurrentPrices({ region: 'us_ct' })).rejects.toThrow(ApiClientError)

    try {
      await getCurrentPrices({ region: 'us_ct' })
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
    await expect(getCurrentPrices({ region: 'us_ct' })).rejects.toThrow(TypeError)
  })
})
