import React from 'react'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PriceLineChart } from '@/components/charts/PriceLineChart'
import '@testing-library/jest-dom'

// Mock recharts to avoid jsdom SVG/canvas dimension warnings from ResponsiveContainer
jest.mock('recharts', () => {
  const MockResponsiveContainer = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  )
  const MockLineChart = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  )
  const MockLine = ({ dataKey }: { dataKey: string }) => (
    <div data-testid={`line-${dataKey}`} />
  )
  const MockXAxis = () => <div data-testid="x-axis" />
  const MockYAxis = () => <div data-testid="y-axis" />
  const MockCartesianGrid = () => <div data-testid="cartesian-grid" />
  const MockTooltip = () => <div data-testid="tooltip" />
  const MockLegend = () => <div data-testid="legend" />
  const MockReferenceLine = () => <div data-testid="reference-line" />
  const MockReferenceArea = () => <div data-testid="reference-area" />

  return {
    ResponsiveContainer: MockResponsiveContainer,
    LineChart: MockLineChart,
    Line: MockLine,
    XAxis: MockXAxis,
    YAxis: MockYAxis,
    CartesianGrid: MockCartesianGrid,
    Tooltip: MockTooltip,
    Legend: MockLegend,
    ReferenceLine: MockReferenceLine,
    ReferenceArea: MockReferenceArea,
  }
})

// Mock date-fns to get stable output independent of wall-clock time
jest.mock('date-fns', () => ({
  format: jest.fn((_date: Date, formatStr: string) => {
    if (formatStr === 'HH:mm') return '00:00'
    return '2026-02-06'
  }),
  parseISO: jest.fn((str: string) => new Date(str)),
}))

jest.mock('@/lib/utils/format', () => ({
  formatCurrency: (amount: number) => `$${amount.toFixed(2)}`,
}))

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

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

  it('renders forecast line when showForecast is enabled', () => {
    render(<PriceLineChart data={mockPriceData} showForecast />)

    expect(screen.getByTestId('line-forecast')).toBeInTheDocument()
    expect(screen.getByTestId('legend')).toBeInTheDocument()
  })

  it('does not render forecast line when showForecast is disabled', () => {
    render(<PriceLineChart data={mockPriceData} />)

    expect(screen.queryByTestId('line-forecast')).not.toBeInTheDocument()
    expect(screen.queryByTestId('legend')).not.toBeInTheDocument()
  })

  it('always renders the actual price line', () => {
    render(<PriceLineChart data={mockPriceData} />)

    expect(screen.getByTestId('line-price')).toBeInTheDocument()
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

    // Should show optimal period indicator badge
    expect(screen.getByText(/cheap/i)).toBeInTheDocument()
  })

  it('renders reference areas for optimal periods', () => {
    const dataWithOptimal = mockPriceData.map((d) => ({
      ...d,
      isOptimal: d.price ? d.price < 0.22 : false,
    }))

    render(<PriceLineChart data={dataWithOptimal} highlightOptimal />)

    expect(screen.getAllByTestId('reference-area').length).toBeGreaterThan(0)
  })

  it('handles empty data gracefully', () => {
    render(<PriceLineChart data={[]} />)

    // Should show empty state
    expect(screen.getByText(/no data available/i)).toBeInTheDocument()
  })

  it('does not render the recharts chart in the empty state', () => {
    render(<PriceLineChart data={[]} />)

    expect(screen.queryByTestId('responsive-container')).not.toBeInTheDocument()
  })

  it('shows loading state while fetching', () => {
    render(<PriceLineChart data={[]} loading />)

    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('does not render the recharts chart in the loading state', () => {
    render(<PriceLineChart data={[]} loading />)

    expect(screen.queryByTestId('responsive-container')).not.toBeInTheDocument()
  })

  it('updates in real-time when new data arrives', async () => {
    const { rerender } = render(<PriceLineChart data={mockPriceData} showCurrentPrice />)

    // Simulate real-time update with a new lowest price
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

  it('renders all time range buttons when onTimeRangeChange is provided', () => {
    const onTimeRangeChange = jest.fn()

    render(
      <PriceLineChart
        data={mockPriceData}
        timeRange="24h"
        onTimeRangeChange={onTimeRangeChange}
      />
    )

    expect(screen.getByRole('button', { name: '6h' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '12h' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '24h' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '48h' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '7d' })).toBeInTheDocument()
  })

  it('does not render time range buttons when onTimeRangeChange is absent', () => {
    render(<PriceLineChart data={mockPriceData} />)

    expect(screen.queryByRole('button', { name: '6h' })).not.toBeInTheDocument()
  })

  it('marks the active time range button as pressed', () => {
    render(
      <PriceLineChart
        data={mockPriceData}
        timeRange="12h"
        onTimeRangeChange={jest.fn()}
      />
    )

    expect(screen.getByRole('button', { name: '12h' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '24h' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows current price prominently', () => {
    render(<PriceLineChart data={mockPriceData} showCurrentPrice />)

    expect(screen.getByTestId('current-price')).toBeInTheDocument()
    expect(screen.getByText('/kWh')).toBeInTheDocument()
  })

  it('does not render current price when showCurrentPrice is false', () => {
    render(<PriceLineChart data={mockPriceData} />)

    expect(screen.queryByTestId('current-price')).not.toBeInTheDocument()
  })

  it('displays price trend indicator', () => {
    render(<PriceLineChart data={mockPriceData} showTrend />)

    // With decreasing prices (0.25 → 0.23 → 0.20), should show trend indicator
    expect(screen.getByTestId('price-trend')).toBeInTheDocument()
  })

  it('does not render trend indicator when showTrend is false', () => {
    render(<PriceLineChart data={mockPriceData} />)

    expect(screen.queryByTestId('price-trend')).not.toBeInTheDocument()
  })

  it('shows stable trend when prices do not move by more than 1%', () => {
    // Two identical prices → 0% change → stable
    const flatData = [
      { time: '2026-02-06T00:00:00Z', price: 0.20, forecast: null },
      { time: '2026-02-06T01:00:00Z', price: 0.20, forecast: null },
    ]

    render(<PriceLineChart data={flatData} showTrend />)

    const trend = screen.getByTestId('price-trend')
    expect(trend).toHaveTextContent(/stable/)
  })

  it('shows increasing trend when price rises by more than 1%', () => {
    const risingData = [
      { time: '2026-02-06T00:00:00Z', price: 0.20, forecast: null },
      { time: '2026-02-06T01:00:00Z', price: 0.25, forecast: null },
    ]

    render(<PriceLineChart data={risingData} showTrend />)

    const trend = screen.getByTestId('price-trend')
    expect(trend).toHaveTextContent(/increasing/)
  })

  it('shows decreasing trend when price falls by more than 1%', () => {
    render(<PriceLineChart data={mockPriceData} showTrend />)

    const trend = screen.getByTestId('price-trend')
    expect(trend).toHaveTextContent(/decreasing/)
  })

  it('does not show current price when all data points have null price', () => {
    const forecastOnly = [
      { time: '2026-02-06T03:00:00Z', price: null, forecast: 0.18 },
    ]

    render(<PriceLineChart data={forecastOnly} showCurrentPrice />)

    // currentPrice will be null so the element should not render
    expect(screen.queryByTestId('current-price')).not.toBeInTheDocument()
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

  it('applies custom className to the outer container', () => {
    render(<PriceLineChart data={mockPriceData} className="my-custom-class" />)

    const container = screen.getByTestId('price-chart-container')
    expect(container).toHaveClass('my-custom-class')
  })

  it('renders the chart inside a ResponsiveContainer', () => {
    render(<PriceLineChart data={mockPriceData} />)

    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })
})
