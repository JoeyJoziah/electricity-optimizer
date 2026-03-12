import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PropaneDashboard } from '@/components/propane/PropaneDashboard'
import '@testing-library/jest-dom'

const mockUsePropanePrices = jest.fn()
jest.mock('@/lib/hooks/usePropane', () => ({
  usePropanePrices: (...args: unknown[]) => mockUsePropanePrices(...args),
}))

jest.mock('@/components/propane/PropanePriceHistory', () => ({
  PropanePriceHistory: ({ state }: { state: string }) => (
    <div data-testid="propane-price-history">History: {state}</div>
  ),
}))
jest.mock('@/components/propane/FillUpTiming', () => ({
  FillUpTiming: ({ state }: { state: string }) => (
    <div data-testid="fill-up-timing">Timing: {state}</div>
  ),
}))

const mockPrices = {
  prices: [
    { state: 'US', price_per_gallon: 2.6, period_date: '2026-03-03' },
    { state: 'CT', price_per_gallon: 2.85, period_date: '2026-03-03' },
    { state: 'MA', price_per_gallon: 2.5, period_date: '2026-03-03' },
    { state: 'NY', price_per_gallon: 2.7, period_date: '2026-03-03' },
  ],
  tracked_states: ['CT', 'MA', 'NY'],
}

describe('PropaneDashboard', () => {
  beforeEach(() => {
    mockUsePropanePrices.mockReset()
  })

  it('shows loading skeletons while data is loading', () => {
    mockUsePropanePrices.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    })
    const { container } = render(<PropaneDashboard />)
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(3)
  })

  it('shows error message on failure', () => {
    mockUsePropanePrices.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Network error'),
    })
    render(<PropaneDashboard />)
    expect(screen.getByText(/Unable to load propane prices/)).toBeInTheDocument()
  })

  it('renders national average price', () => {
    mockUsePropanePrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<PropaneDashboard />)
    expect(screen.getByText('National Average')).toBeInTheDocument()
    expect(screen.getByText('$2.60/gallon')).toBeInTheDocument()
    expect(screen.getByText('Week of 2026-03-03')).toBeInTheDocument()
  })

  it('renders state price cards', () => {
    mockUsePropanePrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<PropaneDashboard />)
    expect(screen.getAllByText('Connecticut').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('Massachusetts').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('$2.85/gal')).toBeInTheDocument()
    expect(screen.getByText('$2.50/gal')).toBeInTheDocument()
  })

  it('shows percentage difference from national average', () => {
    mockUsePropanePrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<PropaneDashboard />)
    // CT: (2.85-2.6)/2.6 = +9.6%
    expect(screen.getByText('+9.6%')).toBeInTheDocument()
    // MA: (2.5-2.6)/2.6 = -3.8%
    expect(screen.getByText('-3.8%')).toBeInTheDocument()
  })

  it('renders state selector dropdown', () => {
    mockUsePropanePrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<PropaneDashboard />)
    const select = screen.getByLabelText('Select State')
    expect(select).toBeInTheDocument()
    expect(screen.getByText('All States')).toBeInTheDocument()
  })

  it('shows detail sections when a state card is clicked', async () => {
    const user = userEvent.setup()
    mockUsePropanePrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<PropaneDashboard />)

    const ctCards = screen.getAllByText('Connecticut')
    const cardElement = ctCards.find(el => el.tagName === 'P')!
    await user.click(cardElement)

    expect(screen.getByTestId('propane-price-history')).toHaveTextContent('History: CT')
    expect(screen.getByTestId('fill-up-timing')).toHaveTextContent('Timing: CT')
  })

  it('filters state cards when a state is selected from dropdown', async () => {
    const user = userEvent.setup()
    mockUsePropanePrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<PropaneDashboard />)

    await user.selectOptions(screen.getByLabelText('Select State'), 'MA')

    expect(screen.getByText('$2.50/gal')).toBeInTheDocument()
    expect(screen.queryByText('$2.85/gal')).not.toBeInTheDocument()
    expect(screen.queryByText('$2.70/gal')).not.toBeInTheDocument()
  })

  it('does not show detail sections when no state is selected', () => {
    mockUsePropanePrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<PropaneDashboard />)
    expect(screen.queryByTestId('propane-price-history')).not.toBeInTheDocument()
    expect(screen.queryByTestId('fill-up-timing')).not.toBeInTheDocument()
  })

  it('handles empty prices gracefully', () => {
    mockUsePropanePrices.mockReturnValue({
      data: { prices: [], tracked_states: [] },
      isLoading: false,
      error: null,
    })
    render(<PropaneDashboard />)
    expect(screen.queryByText('National Average')).not.toBeInTheDocument()
  })
})
