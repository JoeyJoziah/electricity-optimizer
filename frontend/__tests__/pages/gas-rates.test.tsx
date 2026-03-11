import { render, screen, waitFor } from '@testing-library/react'
import GasRatesPage from '@/app/(app)/gas-rates/page'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import React from 'react'

// Mock settings store
jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      region: 'us_ct',
      utilityTypes: ['electricity', 'natural_gas'],
      priceAlerts: [],
    }),
}))

// Mock API modules
const mockGetGasRates = jest.fn()
const mockGetGasHistory = jest.fn()
const mockGetGasStats = jest.fn()
const mockGetDeregulatedGasStates = jest.fn()
const mockCompareGasSuppliers = jest.fn()

jest.mock('@/lib/api/gas-rates', () => ({
  getGasRates: (...args: unknown[]) => mockGetGasRates(...args),
  getGasHistory: (...args: unknown[]) => mockGetGasHistory(...args),
  getGasStats: (...args: unknown[]) => mockGetGasStats(...args),
  getDeregulatedGasStates: (...args: unknown[]) => mockGetDeregulatedGasStates(...args),
  compareGasSuppliers: (...args: unknown[]) => mockCompareGasSuppliers(...args),
}))

const defaultRatesResponse = {
  region: 'us_ct',
  utility_type: 'natural_gas',
  unit: '$/therm',
  is_deregulated: true,
  count: 1,
  prices: [
    { id: '1', supplier: 'EIA Average', price: '1.2500', unit: '$/therm', timestamp: '2026-03-10T00:00:00Z', source: 'eia' },
  ],
}

const defaultStatsResponse = {
  region: 'us_ct',
  utility_type: 'natural_gas',
  unit: '$/therm',
  avg_price: '1.2250',
  min_price: '1.2000',
  max_price: '1.2500',
  count: 2,
}

const defaultHistoryResponse = {
  region: 'us_ct',
  utility_type: 'natural_gas',
  period_days: 90,
  count: 2,
  prices: [
    { price: '1.2500', timestamp: '2026-03-10T00:00:00Z', supplier: 'EIA Average' },
    { price: '1.2000', timestamp: '2026-03-03T00:00:00Z', supplier: 'EIA Average' },
  ],
}

const defaultCompareResponse = {
  region: 'us_ct',
  is_deregulated: true,
  unit: '$/therm',
  suppliers: [
    { supplier: 'Direct Energy', price: '1.1000', timestamp: '2026-03-10T00:00:00Z', source: 'eia' },
    { supplier: 'Constellation', price: '1.2500', timestamp: '2026-03-10T00:00:00Z', source: 'eia' },
  ],
  cheapest: 'Direct Energy',
}

describe('GasRatesPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })

    mockGetGasRates.mockResolvedValue(defaultRatesResponse)
    mockGetGasHistory.mockResolvedValue(defaultHistoryResponse)
    mockGetGasStats.mockResolvedValue(defaultStatsResponse)
    mockGetDeregulatedGasStates.mockResolvedValue({ count: 2, states: [] })
    mockCompareGasSuppliers.mockResolvedValue(defaultCompareResponse)
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('renders the page title', async () => {
    render(<GasRatesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Natural Gas Rates')).toBeInTheDocument()
    })
  })

  it('renders current gas rate', async () => {
    render(<GasRatesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Current Rate')).toBeInTheDocument()
      // Multiple elements contain 1.25 (current, high, history, compare)
      expect(screen.getAllByText(/1\.25/).length).toBeGreaterThan(0)
    })
  })

  it('renders deregulated market badge', async () => {
    render(<GasRatesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/Deregulated market/)).toBeInTheDocument()
    })
  })

  it('renders 30-day stats', async () => {
    render(<GasRatesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('30-Day Average')).toBeInTheDocument()
      expect(screen.getByText('30-Day Low')).toBeInTheDocument()
      expect(screen.getByText('30-Day High')).toBeInTheDocument()
    })
  })

  it('renders price history section', async () => {
    render(<GasRatesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Price History (90 days)')).toBeInTheDocument()
      // History entries show EIA Average as supplier
      expect(screen.getAllByText('EIA Average').length).toBeGreaterThan(0)
    })
  })

  it('renders supplier comparison for deregulated state', async () => {
    render(<GasRatesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Supplier Comparison')).toBeInTheDocument()
      expect(screen.getByText('Direct Energy')).toBeInTheDocument()
      expect(screen.getByText('Constellation')).toBeInTheDocument()
      expect(screen.getByText('Cheapest')).toBeInTheDocument()
    })
  })

  it('handles empty data gracefully', async () => {
    mockGetGasRates.mockResolvedValue({
      ...defaultRatesResponse,
      count: 0,
      prices: [],
    })
    mockGetGasHistory.mockResolvedValue({
      ...defaultHistoryResponse,
      count: 0,
      prices: [],
    })
    mockGetGasStats.mockResolvedValue({
      ...defaultStatsResponse,
      avg_price: null,
      min_price: null,
      max_price: null,
      count: 0,
    })

    render(<GasRatesPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getAllByText('--').length).toBeGreaterThan(0)
      expect(screen.getByText(/No price history available/)).toBeInTheDocument()
    })
  })

  it('renders loading skeletons', () => {
    mockGetGasRates.mockReturnValue(new Promise(() => {}))
    mockGetGasHistory.mockReturnValue(new Promise(() => {}))
    mockGetGasStats.mockReturnValue(new Promise(() => {}))
    mockCompareGasSuppliers.mockReturnValue(new Promise(() => {}))

    render(<GasRatesPage />, { wrapper })

    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows no-region message when region is null', () => {
    // Override mock to return null region
    jest.spyOn(require('@/lib/store/settings'), 'useSettingsStore').mockImplementation(
      (selector: (state: Record<string, unknown>) => unknown) =>
        selector({ region: null, utilityTypes: [], priceAlerts: [] })
    )

    render(<GasRatesPage />, { wrapper })

    expect(screen.getByText('No region set')).toBeInTheDocument()
    expect(screen.getByText(/Set your region in Settings/)).toBeInTheDocument()
  })
})
