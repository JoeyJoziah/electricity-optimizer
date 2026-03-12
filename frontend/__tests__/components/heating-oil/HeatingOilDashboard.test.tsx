import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HeatingOilDashboard } from '@/components/heating-oil/HeatingOilDashboard'
import '@testing-library/jest-dom'

const mockUseHeatingOilPrices = jest.fn()
jest.mock('@/lib/hooks/useHeatingOil', () => ({
  useHeatingOilPrices: (...args: unknown[]) => mockUseHeatingOilPrices(...args),
}))

// Mock child components to isolate dashboard logic
jest.mock('@/components/heating-oil/OilPriceHistory', () => ({
  OilPriceHistory: ({ state }: { state: string }) => (
    <div data-testid="oil-price-history">History: {state}</div>
  ),
}))
jest.mock('@/components/heating-oil/DealerList', () => ({
  DealerList: ({ state }: { state: string }) => (
    <div data-testid="dealer-list">Dealers: {state}</div>
  ),
}))

const mockPrices = {
  prices: [
    { state: 'US', price_per_gallon: 3.5, period_date: '2026-03-03' },
    { state: 'CT', price_per_gallon: 3.65, period_date: '2026-03-03' },
    { state: 'MA', price_per_gallon: 3.4, period_date: '2026-03-03' },
    { state: 'NY', price_per_gallon: 3.55, period_date: '2026-03-03' },
  ],
  tracked_states: ['CT', 'MA', 'NY'],
}

describe('HeatingOilDashboard', () => {
  beforeEach(() => {
    mockUseHeatingOilPrices.mockReset()
  })

  it('shows loading skeletons while data is loading', () => {
    mockUseHeatingOilPrices.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    })
    const { container } = render(<HeatingOilDashboard />)
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(3)
  })

  it('shows error message on failure', () => {
    mockUseHeatingOilPrices.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Network error'),
    })
    render(<HeatingOilDashboard />)
    expect(screen.getByText(/Unable to load heating oil prices/)).toBeInTheDocument()
  })

  it('renders national average price', () => {
    mockUseHeatingOilPrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<HeatingOilDashboard />)
    expect(screen.getByText('National Average')).toBeInTheDocument()
    expect(screen.getByText('$3.50/gallon')).toBeInTheDocument()
    expect(screen.getByText('Week of 2026-03-03')).toBeInTheDocument()
  })

  it('renders state price cards', () => {
    mockUseHeatingOilPrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<HeatingOilDashboard />)
    // State names appear in both dropdown and cards — use getAllByText
    expect(screen.getAllByText('Connecticut').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('Massachusetts').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('$3.65/gal')).toBeInTheDocument()
    expect(screen.getByText('$3.40/gal')).toBeInTheDocument()
  })

  it('shows percentage difference from national average', () => {
    mockUseHeatingOilPrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<HeatingOilDashboard />)
    // CT: (3.65-3.5)/3.5 = +4.3%
    expect(screen.getByText('+4.3%')).toBeInTheDocument()
    // MA: (3.4-3.5)/3.5 = -2.9%
    expect(screen.getByText('-2.9%')).toBeInTheDocument()
  })

  it('renders state selector dropdown', () => {
    mockUseHeatingOilPrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<HeatingOilDashboard />)
    const select = screen.getByLabelText('Select State')
    expect(select).toBeInTheDocument()
    expect(screen.getByText('All States')).toBeInTheDocument()
  })

  it('shows detail sections when a state card is clicked', async () => {
    const user = userEvent.setup()
    mockUseHeatingOilPrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<HeatingOilDashboard />)

    // Click the price card (p.font-semibold), not the dropdown option
    const ctCards = screen.getAllByText('Connecticut')
    const cardElement = ctCards.find(el => el.tagName === 'P')!
    await user.click(cardElement)

    expect(screen.getByTestId('oil-price-history')).toHaveTextContent('History: CT')
    expect(screen.getByTestId('dealer-list')).toHaveTextContent('Dealers: CT')
  })

  it('filters state cards when a state is selected from dropdown', async () => {
    const user = userEvent.setup()
    mockUseHeatingOilPrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<HeatingOilDashboard />)

    await user.selectOptions(screen.getByLabelText('Select State'), 'MA')

    // MA card still visible, CT/NY cards hidden (only dropdown options remain)
    expect(screen.getByText('$3.40/gal')).toBeInTheDocument()
    expect(screen.queryByText('$3.65/gal')).not.toBeInTheDocument()
    expect(screen.queryByText('$3.55/gal')).not.toBeInTheDocument()
  })

  it('does not show detail sections when no state is selected', () => {
    mockUseHeatingOilPrices.mockReturnValue({
      data: mockPrices,
      isLoading: false,
      error: null,
    })
    render(<HeatingOilDashboard />)
    expect(screen.queryByTestId('oil-price-history')).not.toBeInTheDocument()
    expect(screen.queryByTestId('dealer-list')).not.toBeInTheDocument()
  })

  it('handles empty prices gracefully', () => {
    mockUseHeatingOilPrices.mockReturnValue({
      data: { prices: [], tracked_states: [] },
      isLoading: false,
      error: null,
    })
    render(<HeatingOilDashboard />)
    expect(screen.queryByText('National Average')).not.toBeInTheDocument()
  })
})
