import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// --- Mocks ---

let mockRegion: string | null = 'us_ct'

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (s: { region: string | null }) => unknown) =>
    selector({ region: mockRegion }),
}))

jest.mock('@/components/layout/Header', () => ({
  Header: ({ title }: { title: string }) => (
    <div data-testid="header">{title}</div>
  ),
}))

jest.mock('@/components/ui/skeleton', () => ({
  Skeleton: (props: Record<string, unknown>) => (
    <div data-testid="skeleton" {...props} />
  ),
}))

jest.mock('@/components/ui/card', () => ({
  Card: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="card" className={className}>{children}</div>
  ),
  CardHeader: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="card-header">{children}</div>
  ),
  CardTitle: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <h3 data-testid="card-title" className={className}>{children}</h3>
  ),
  CardContent: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="card-content" className={className}>{children}</div>
  ),
}))

jest.mock('@/components/ui/badge', () => ({
  Badge: ({
    children,
    variant,
    className,
  }: {
    children: React.ReactNode
    variant?: string
    className?: string
  }) => (
    <span data-testid="badge" data-variant={variant} className={className}>
      {children}
    </span>
  ),
}))

jest.mock('@/lib/utils/format', () => ({
  formatCurrency: (n: number) => `$${n.toFixed(2)}`,
  formatDateTime: (d: string) => d,
}))

const mockRatesData = {
  prices: [
    { price: '1.25', source: 'EIA', timestamp: '2026-03-10', supplier: 'Default' },
  ],
  is_deregulated: true,
  unit: 'therm',
}

const mockStatsData = {
  avg_price: '1.20',
  min_price: '1.00',
  max_price: '1.50',
  unit: 'therm',
}

const mockHistoryData = {
  prices: [
    { price: '1.25', supplier: 'SupplierA', timestamp: '2026-03-10' },
    { price: '1.18', supplier: 'SupplierB', timestamp: '2026-03-08' },
  ],
  count: 2,
}

const mockCompareData = {
  suppliers: [
    { supplier: 'CheapGas', price: '1.10', timestamp: '2026-03-10' },
    { supplier: 'OtherGas', price: '1.30', timestamp: '2026-03-09' },
  ],
}

let mockRatesLoading = false
let mockStatsLoading = false
let mockHistoryLoading = false
let mockCompareLoading = false
let currentRatesData: typeof mockRatesData | undefined = mockRatesData
let currentStatsData: typeof mockStatsData | undefined = mockStatsData
let currentHistoryData: typeof mockHistoryData | undefined = mockHistoryData
let currentCompareData: typeof mockCompareData | undefined = mockCompareData

jest.mock('@/lib/hooks/useGasRates', () => ({
  useGasRates: () => ({
    data: mockRatesLoading ? undefined : currentRatesData,
    isLoading: mockRatesLoading,
  }),
  useGasHistory: () => ({
    data: mockHistoryLoading ? undefined : currentHistoryData,
    isLoading: mockHistoryLoading,
  }),
  useGasStats: () => ({
    data: mockStatsLoading ? undefined : currentStatsData,
    isLoading: mockStatsLoading,
  }),
  useGasSupplierComparison: () => ({
    data: mockCompareLoading ? undefined : currentCompareData,
    isLoading: mockCompareLoading,
  }),
}))

import GasRatesContent from '@/components/gas/GasRatesContent'

describe('GasRatesContent', () => {
  beforeEach(() => {
    mockRegion = 'us_ct'
    mockRatesLoading = false
    mockStatsLoading = false
    mockHistoryLoading = false
    mockCompareLoading = false
    currentRatesData = mockRatesData
    currentStatsData = mockStatsData
    currentHistoryData = mockHistoryData
    currentCompareData = mockCompareData
    jest.clearAllMocks()
  })

  it('renders header with title', () => {
    render(<GasRatesContent />)

    expect(screen.getByTestId('header')).toHaveTextContent(
      'Natural Gas Rates'
    )
  })

  it('shows no region message when region is null', () => {
    mockRegion = null

    render(<GasRatesContent />)

    expect(screen.getByText('No region set')).toBeInTheDocument()
    expect(
      screen.getByText(/Set your region in Settings/)
    ).toBeInTheDocument()
  })

  it('shows deregulated market badge', () => {
    render(<GasRatesContent />)

    expect(
      screen.getByText(/Deregulated market/)
    ).toBeInTheDocument()
  })

  it('shows regulated market badge for non-deregulated state', () => {
    currentRatesData = { ...mockRatesData, is_deregulated: false }

    render(<GasRatesContent />)

    expect(screen.getByText(/Regulated market/)).toBeInTheDocument()
  })

  it('renders current rate', () => {
    render(<GasRatesContent />)

    expect(screen.getByText('Current Rate')).toBeInTheDocument()
    expect(screen.getByText('$1.25')).toBeInTheDocument()
  })

  it('renders 30-day average', () => {
    render(<GasRatesContent />)

    expect(screen.getByText('30-Day Average')).toBeInTheDocument()
    expect(screen.getByText('$1.20')).toBeInTheDocument()
  })

  it('renders 30-day low', () => {
    render(<GasRatesContent />)

    expect(screen.getByText('30-Day Low')).toBeInTheDocument()
    expect(screen.getByText('$1.00')).toBeInTheDocument()
  })

  it('renders 30-day high', () => {
    render(<GasRatesContent />)

    expect(screen.getByText('30-Day High')).toBeInTheDocument()
    expect(screen.getByText('$1.50')).toBeInTheDocument()
  })

  it('renders price history', () => {
    render(<GasRatesContent />)

    expect(screen.getByText(/Price History/)).toBeInTheDocument()
    expect(screen.getByText('SupplierA')).toBeInTheDocument()
    expect(screen.getByText('SupplierB')).toBeInTheDocument()
  })

  it('renders supplier comparison for deregulated markets', () => {
    render(<GasRatesContent />)

    expect(screen.getByText('Supplier Comparison')).toBeInTheDocument()
    expect(screen.getByText('CheapGas')).toBeInTheDocument()
    expect(screen.getByText('OtherGas')).toBeInTheDocument()
  })

  it('renders Cheapest badge on first supplier', () => {
    render(<GasRatesContent />)

    expect(screen.getByText('Cheapest')).toBeInTheDocument()
  })

  it('hides supplier comparison for regulated markets', () => {
    currentRatesData = { ...mockRatesData, is_deregulated: false }

    render(<GasRatesContent />)

    expect(screen.queryByText('Supplier Comparison')).not.toBeInTheDocument()
  })

  it('shows skeletons when rates are loading', () => {
    mockRatesLoading = true
    currentRatesData = undefined

    render(<GasRatesContent />)

    const skeletons = screen.getAllByTestId('skeleton')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows empty state when no price history', () => {
    currentHistoryData = { prices: [], count: 0 }

    render(<GasRatesContent />)

    expect(
      screen.getByText(/No price history available/)
    ).toBeInTheDocument()
  })

  it('shows trend indicator (CSS capitalize, DOM lowercase)', () => {
    // price 1.25 > avg 1.20 * 1.02 = 1.224 -> trend = "increasing"
    render(<GasRatesContent />)

    // The component renders trend as lowercase with CSS capitalize
    expect(screen.getByText('increasing')).toBeInTheDocument()
  })

  it('shows record count when more than 20', () => {
    currentHistoryData = {
      prices: Array.from({ length: 20 }, (_, i) => ({
        price: `${1 + i * 0.01}`,
        supplier: `Supplier${i}`,
        timestamp: `2026-03-${String(i + 1).padStart(2, '0')}`,
      })),
      count: 45,
    }

    render(<GasRatesContent />)

    expect(screen.getByText(/Showing 20 of 45 records/)).toBeInTheDocument()
  })
})
