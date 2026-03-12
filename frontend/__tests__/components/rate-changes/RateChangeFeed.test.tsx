import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RateChangeFeed } from '@/components/rate-changes/RateChangeFeed'
import '@testing-library/jest-dom'

// Mock the hook
const mockUseRateChanges = jest.fn()
jest.mock('@/lib/hooks/useRateChanges', () => ({
  useRateChanges: (params: unknown) => mockUseRateChanges(params),
}))

// Mock child component
jest.mock('@/components/rate-changes/RateChangeCard', () => ({
  RateChangeCard: ({ change }: { change: { id: string; supplier: string } }) => (
    <div data-testid="rate-change-card">{change.supplier}</div>
  ),
}))

const mockChanges = [
  {
    id: 'rc-1',
    utility_type: 'electricity',
    region: 'us_ct',
    supplier: 'Eversource',
    previous_price: 0.1,
    current_price: 0.12,
    change_pct: 20.0,
    change_direction: 'increase',
    detected_at: '2026-03-10T06:30:00Z',
    recommendation_supplier: null,
    recommendation_price: null,
    recommendation_savings: null,
  },
  {
    id: 'rc-2',
    utility_type: 'natural_gas',
    region: 'TX',
    supplier: 'TXU',
    previous_price: 1.0,
    current_price: 0.8,
    change_pct: -20.0,
    change_direction: 'decrease',
    detected_at: '2026-03-09T06:30:00Z',
    recommendation_supplier: null,
    recommendation_price: null,
    recommendation_savings: null,
  },
]

describe('RateChangeFeed', () => {
  beforeEach(() => {
    mockUseRateChanges.mockReset()
  })

  it('shows loading skeletons', () => {
    mockUseRateChanges.mockReturnValue({ isLoading: true, data: null, error: null })
    render(<RateChangeFeed />)
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(3)
  })

  it('shows error message', () => {
    mockUseRateChanges.mockReturnValue({
      isLoading: false,
      data: null,
      error: new Error('fail'),
    })
    render(<RateChangeFeed />)
    expect(screen.getByText(/Failed to load rate changes/)).toBeInTheDocument()
  })

  it('shows empty state message', () => {
    mockUseRateChanges.mockReturnValue({
      isLoading: false,
      data: { changes: [], total: 0 },
      error: null,
    })
    render(<RateChangeFeed />)
    expect(screen.getByText(/No rate changes detected/)).toBeInTheDocument()
  })

  it('renders rate change cards', () => {
    mockUseRateChanges.mockReturnValue({
      isLoading: false,
      data: { changes: mockChanges, total: 2 },
      error: null,
    })
    render(<RateChangeFeed />)
    const cards = screen.getAllByTestId('rate-change-card')
    expect(cards).toHaveLength(2)
    expect(screen.getByText('Eversource')).toBeInTheDocument()
    expect(screen.getByText('TXU')).toBeInTheDocument()
  })

  it('has utility type filter dropdown', () => {
    mockUseRateChanges.mockReturnValue({
      isLoading: false,
      data: { changes: [], total: 0 },
      error: null,
    })
    render(<RateChangeFeed />)
    const select = screen.getByLabelText('Filter by utility type')
    expect(select).toBeInTheDocument()
  })

  it('has time range filter dropdown', () => {
    mockUseRateChanges.mockReturnValue({
      isLoading: false,
      data: { changes: [], total: 0 },
      error: null,
    })
    render(<RateChangeFeed />)
    const select = screen.getByLabelText('Time range')
    expect(select).toBeInTheDocument()
  })

  it('filters by utility type on selection', async () => {
    mockUseRateChanges.mockReturnValue({
      isLoading: false,
      data: { changes: [], total: 0 },
      error: null,
    })
    render(<RateChangeFeed />)

    const select = screen.getByLabelText('Filter by utility type')
    await userEvent.selectOptions(select, 'electricity')

    // Hook should be called with electricity filter
    expect(mockUseRateChanges).toHaveBeenCalledWith(
      expect.objectContaining({ utility_type: 'electricity' })
    )
  })

  it('changes days filter on selection', async () => {
    mockUseRateChanges.mockReturnValue({
      isLoading: false,
      data: { changes: [], total: 0 },
      error: null,
    })
    render(<RateChangeFeed />)

    const select = screen.getByLabelText('Time range')
    await userEvent.selectOptions(select, '30')

    expect(mockUseRateChanges).toHaveBeenCalledWith(
      expect.objectContaining({ days: 30 })
    )
  })

  it('shows all utility options', () => {
    mockUseRateChanges.mockReturnValue({
      isLoading: false,
      data: { changes: [], total: 0 },
      error: null,
    })
    render(<RateChangeFeed />)
    expect(screen.getByText('All Utilities')).toBeInTheDocument()
    expect(screen.getByText('Electricity')).toBeInTheDocument()
    expect(screen.getByText('Natural Gas')).toBeInTheDocument()
    expect(screen.getByText('Heating Oil')).toBeInTheDocument()
  })

  it('displays empty state with correct day count', () => {
    mockUseRateChanges.mockReturnValue({
      isLoading: false,
      data: { changes: [], total: 0 },
      error: null,
    })
    render(<RateChangeFeed />)
    expect(screen.getByText(/last 7 days/)).toBeInTheDocument()
  })
})
