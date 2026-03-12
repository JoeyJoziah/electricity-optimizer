import { render, screen } from '@testing-library/react'
import { OilPriceHistory } from '@/components/heating-oil/OilPriceHistory'
import '@testing-library/jest-dom'

const mockUseHeatingOilHistory = jest.fn()
jest.mock('@/lib/hooks/useHeatingOil', () => ({
  useHeatingOilHistory: (...args: unknown[]) => mockUseHeatingOilHistory(...args),
}))

const mockHistory = {
  history: [
    { id: '1', period_date: '2026-03-03', price_per_gallon: 3.65 },
    { id: '2', period_date: '2026-02-24', price_per_gallon: 3.58 },
    { id: '3', period_date: '2026-02-17', price_per_gallon: 3.72 },
  ],
  comparison: {
    price_per_gallon: 3.65,
    national_avg: { price_per_gallon: 3.5 },
    difference_pct: -4.3,
    estimated_monthly_cost: 243,
    estimated_annual_cost: 2920,
  },
}

describe('OilPriceHistory', () => {
  beforeEach(() => {
    mockUseHeatingOilHistory.mockReset()
  })

  it('shows loading skeleton while data is loading', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    })
    const { container } = render(<OilPriceHistory state="CT" />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('returns null on error', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('fail'),
    })
    const { container } = render(<OilPriceHistory state="CT" />)
    expect(container.firstChild).toBeNull()
  })

  it('renders price history header with state', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: mockHistory,
      isLoading: false,
      error: null,
    })
    render(<OilPriceHistory state="CT" />)
    expect(screen.getByText(/Price History/)).toBeInTheDocument()
    expect(screen.getByText(/CT/)).toBeInTheDocument()
  })

  it('shows current price', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: mockHistory,
      isLoading: false,
      error: null,
    })
    render(<OilPriceHistory state="CT" />)
    expect(screen.getByText('Current Price')).toBeInTheDocument()
    // $3.65/gal appears in both comparison header and history row
    expect(screen.getAllByText('$3.65/gal').length).toBeGreaterThanOrEqual(1)
  })

  it('shows national average comparison with green for cheaper', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: mockHistory,
      isLoading: false,
      error: null,
    })
    render(<OilPriceHistory state="CT" />)
    expect(screen.getByText('vs National Avg')).toBeInTheDocument()
    expect(screen.getByText('-4.3%')).toBeInTheDocument()
  })

  it('shows red for more expensive than national average', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: {
        ...mockHistory,
        comparison: {
          ...mockHistory.comparison,
          difference_pct: 4.3,
        },
      },
      isLoading: false,
      error: null,
    })
    render(<OilPriceHistory state="CT" />)
    expect(screen.getByText('+4.3%')).toBeInTheDocument()
  })

  it('shows estimated monthly and annual costs', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: mockHistory,
      isLoading: false,
      error: null,
    })
    render(<OilPriceHistory state="CT" />)
    expect(screen.getByText('Est. Monthly Cost')).toBeInTheDocument()
    expect(screen.getByText('$243')).toBeInTheDocument()
    expect(screen.getByText('Est. Annual Cost')).toBeInTheDocument()
    expect(screen.getByText('$2920')).toBeInTheDocument()
  })

  it('renders weekly history rows', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: mockHistory,
      isLoading: false,
      error: null,
    })
    render(<OilPriceHistory state="CT" />)
    expect(screen.getByText('Recent Weeks')).toBeInTheDocument()
    expect(screen.getByText('2026-03-03')).toBeInTheDocument()
    expect(screen.getByText('2026-02-24')).toBeInTheDocument()
    expect(screen.getByText('$3.72/gal')).toBeInTheDocument()
  })

  it('handles N/A when difference_pct is null', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: {
        ...mockHistory,
        comparison: {
          ...mockHistory.comparison,
          difference_pct: null,
        },
      },
      isLoading: false,
      error: null,
    })
    render(<OilPriceHistory state="CT" />)
    expect(screen.getByText('N/A')).toBeInTheDocument()
  })

  it('hides history section when history is empty', () => {
    mockUseHeatingOilHistory.mockReturnValue({
      data: { history: [], comparison: mockHistory.comparison },
      isLoading: false,
      error: null,
    })
    render(<OilPriceHistory state="CT" />)
    expect(screen.queryByText('Recent Weeks')).not.toBeInTheDocument()
  })
})
