import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PriceLineChart } from '@/components/charts/PriceLineChart'
import '@testing-library/jest-dom'

const mockPriceData = [
  { time: '2026-02-06T00:00:00Z', price: 0.25, forecast: null },
  { time: '2026-02-06T01:00:00Z', price: 0.23, forecast: null },
  { time: '2026-02-06T02:00:00Z', price: 0.20, forecast: null },
  { time: '2026-02-06T03:00:00Z', price: null, forecast: 0.18 },
  { time: '2026-02-06T04:00:00Z', price: null, forecast: 0.19 },
]

describe('PriceLineChart', () => {
  it('renders price chart with data', () => {
    render(<PriceLineChart data={mockPriceData} />)

    // Chart container should be rendered
    expect(screen.getByRole('img', { name: /price chart/i })).toBeInTheDocument()
  })

  it('displays both actual and forecast prices when showForecast is true', () => {
    render(<PriceLineChart data={mockPriceData} showForecast />)

    // Chart aria-label indicates both actual and forecast are shown
    const chart = screen.getByRole('img', { name: /actual and forecast/i })
    expect(chart).toBeInTheDocument()
  })

  it('formats prices in currency format', () => {
    render(<PriceLineChart data={mockPriceData} showCurrentPrice />)

    // Current price is displayed with currency formatting
    const currentPriceEl = screen.getByTestId('current-price')
    expect(currentPriceEl).toBeInTheDocument()
    expect(currentPriceEl).toHaveTextContent(/0\.20/)
  })

  it('highlights optimal time periods when highlightOptimal is true', () => {
    const dataWithOptimal = mockPriceData.map((d) => ({
      ...d,
      isOptimal: d.price ? d.price < 0.22 : false,
    }))

    render(<PriceLineChart data={dataWithOptimal} highlightOptimal />)

    // Should show optimal period indicator
    expect(screen.getByText(/cheap/i)).toBeInTheDocument()
  })

  it('handles empty data gracefully', () => {
    render(<PriceLineChart data={[]} />)

    // Should show empty state
    expect(screen.getByText(/no data available/i)).toBeInTheDocument()
  })

  it('shows loading state while fetching', () => {
    render(<PriceLineChart data={[]} loading />)

    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('updates in real-time when new data arrives', async () => {
    const { rerender } = render(<PriceLineChart data={mockPriceData} showCurrentPrice />)

    // Simulate real-time update
    const updatedData = [
      ...mockPriceData,
      { time: '2026-02-06T05:00:00Z', price: 0.17, forecast: null },
    ]

    rerender(<PriceLineChart data={updatedData} showCurrentPrice />)

    await waitFor(() => {
      const currentPriceEl = screen.getByTestId('current-price')
      expect(currentPriceEl).toHaveTextContent(/0\.17/)
    })
  })

  it('supports time range selection', async () => {
    const onTimeRangeChange = jest.fn()
    const user = userEvent.setup()

    render(
      <PriceLineChart
        data={mockPriceData}
        timeRange="24h"
        onTimeRangeChange={onTimeRangeChange}
      />
    )

    const button24h = screen.getByRole('button', { name: /24h/i })
    expect(button24h).toBeInTheDocument()

    // Click on 6h button
    const button6h = screen.getByRole('button', { name: /6h/i })
    await user.click(button6h)

    expect(onTimeRangeChange).toHaveBeenCalledWith('6h')
  })

  it('shows current price prominently', () => {
    render(<PriceLineChart data={mockPriceData} showCurrentPrice />)

    expect(screen.getByTestId('current-price')).toBeInTheDocument()
  })

  it('displays price trend indicator', () => {
    render(<PriceLineChart data={mockPriceData} showTrend />)

    // With decreasing prices, should show trend indicator
    expect(screen.getByTestId('price-trend')).toBeInTheDocument()
  })

  it('is accessible with proper ARIA labels', () => {
    render(<PriceLineChart data={mockPriceData} />)

    const chart = screen.getByRole('img', { name: /price chart/i })
    expect(chart).toHaveAttribute('aria-label')
  })

  it('renders with responsive width', () => {
    render(<PriceLineChart data={mockPriceData} />)

    const container = screen.getByTestId('price-chart-container')
    expect(container).toHaveClass('w-full')
  })
})
