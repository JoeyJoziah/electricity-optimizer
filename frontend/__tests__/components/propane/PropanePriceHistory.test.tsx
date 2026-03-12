import { render, screen } from '@testing-library/react'
import { PropanePriceHistory } from '@/components/propane/PropanePriceHistory'
import '@testing-library/jest-dom'

const mockUsePropaneHistory = jest.fn()
jest.mock('@/lib/hooks/usePropane', () => ({
  usePropaneHistory: (...args: unknown[]) => mockUsePropaneHistory(...args),
}))

describe('PropanePriceHistory', () => {
  beforeEach(() => {
    mockUsePropaneHistory.mockReset()
  })

  it('shows loading skeleton', () => {
    mockUsePropaneHistory.mockReturnValue({ data: null, isLoading: true, error: null })
    const { container } = render(<PropanePriceHistory state="CT" />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders nothing on error', () => {
    mockUsePropaneHistory.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') })
    const { container } = render(<PropanePriceHistory state="CT" />)
    expect(container.innerHTML).toBe('')
  })

  it('renders comparison data', () => {
    mockUsePropaneHistory.mockReturnValue({
      data: {
        state: 'CT',
        weeks: 12,
        history: [],
        comparison: {
          state: 'CT',
          price_per_gallon: 2.85,
          national_avg: 2.6,
          difference_pct: 9.62,
          estimated_monthly_cost: 178,
          estimated_annual_cost: 2138,
        },
      },
      isLoading: false,
      error: null,
    })
    render(<PropanePriceHistory state="CT" />)
    expect(screen.getByText('$2.85/gal')).toBeInTheDocument()
    expect(screen.getByText('+9.62%')).toBeInTheDocument()
    expect(screen.getByText('$178')).toBeInTheDocument()
    expect(screen.getByText('$2138')).toBeInTheDocument()
  })

  it('renders history rows', () => {
    mockUsePropaneHistory.mockReturnValue({
      data: {
        state: 'CT',
        weeks: 12,
        history: [
          { id: '1', price_per_gallon: 2.85, period_date: '2026-03-03' },
          { id: '2', price_per_gallon: 2.9, period_date: '2026-02-24' },
        ],
        comparison: null,
      },
      isLoading: false,
      error: null,
    })
    render(<PropanePriceHistory state="CT" />)
    expect(screen.getByText('2026-03-03')).toBeInTheDocument()
    expect(screen.getByText('$2.85/gal')).toBeInTheDocument()
    expect(screen.getByText('2026-02-24')).toBeInTheDocument()
    expect(screen.getByText('$2.90/gal')).toBeInTheDocument()
  })
})
