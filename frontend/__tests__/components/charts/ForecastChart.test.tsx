import { render, screen } from '@testing-library/react'
import { ForecastChart } from '@/components/charts/ForecastChart'
import '@testing-library/jest-dom'

// Mock recharts to avoid rendering issues in jsdom
jest.mock('recharts', () => {
  const MockResponsiveContainer = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  )
  const MockAreaChart = ({ children, data }: { children: React.ReactNode; data: unknown[] }) => (
    <div data-testid="area-chart" data-points={data.length}>{children}</div>
  )
  const MockArea = ({ dataKey }: { dataKey: string }) => (
    <div data-testid={`area-${dataKey}`} />
  )
  const MockXAxis = () => <div data-testid="x-axis" />
  const MockYAxis = () => <div data-testid="y-axis" />
  const MockCartesianGrid = () => <div data-testid="cartesian-grid" />
  const MockTooltip = () => <div data-testid="tooltip" />
  const MockReferenceLine = ({ label }: { label?: { value: string } }) => (
    <div data-testid="reference-line" data-label={label?.value} />
  )

  return {
    ResponsiveContainer: MockResponsiveContainer,
    AreaChart: MockAreaChart,
    Area: MockArea,
    XAxis: MockXAxis,
    YAxis: MockYAxis,
    CartesianGrid: MockCartesianGrid,
    Tooltip: MockTooltip,
    ReferenceLine: MockReferenceLine,
  }
})

// Mock date-fns to get consistent output
jest.mock('date-fns', () => ({
  format: jest.fn((_date: Date, formatStr: string) => {
    if (formatStr === 'HH:mm') return '14:00'
    return '2026-02-22'
  }),
  parseISO: jest.fn((str: string) => new Date(str)),
  addHours: jest.fn((date: Date, hours: number) => new Date(date.getTime() + hours * 3600000)),
}))

// Mock formatCurrency
jest.mock('@/lib/utils/format', () => ({
  formatCurrency: (amount: number) => `$${amount.toFixed(2)}`,
}))

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

const mockForecast = [
  { hour: 1, price: 0.12, confidence: [0.10, 0.14] as [number, number], timestamp: '2026-02-22T01:00:00Z' },
  { hour: 2, price: 0.15, confidence: [0.13, 0.17] as [number, number], timestamp: '2026-02-22T02:00:00Z' },
  { hour: 3, price: 0.10, confidence: [0.08, 0.12] as [number, number], timestamp: '2026-02-22T03:00:00Z' },
  { hour: 4, price: 0.18, confidence: [0.16, 0.20] as [number, number], timestamp: '2026-02-22T04:00:00Z' },
  { hour: 5, price: 0.14, confidence: [0.12, 0.16] as [number, number], timestamp: '2026-02-22T05:00:00Z' },
]

describe('ForecastChart', () => {
  it('renders empty state when no data provided', () => {
    render(<ForecastChart forecast={[]} />)

    expect(screen.getByText('No forecast data available')).toBeInTheDocument()
  })

  it('renders chart with forecast data', () => {
    render(<ForecastChart forecast={mockForecast} />)

    expect(screen.getByText('24-Hour Forecast')).toBeInTheDocument()
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    expect(screen.getByTestId('area-chart')).toBeInTheDocument()
  })

  it('renders the price area line', () => {
    render(<ForecastChart forecast={mockForecast} />)

    expect(screen.getByTestId('area-price')).toBeInTheDocument()
  })

  it('renders confidence interval areas when showConfidence is true', () => {
    render(<ForecastChart forecast={mockForecast} showConfidence={true} />)

    expect(screen.getByTestId('area-confidenceHigh')).toBeInTheDocument()
    expect(screen.getByTestId('area-confidenceLow')).toBeInTheDocument()
  })

  it('hides confidence interval when showConfidence is false', () => {
    render(<ForecastChart forecast={mockForecast} showConfidence={false} />)

    expect(screen.queryByTestId('area-confidenceHigh')).not.toBeInTheDocument()
    expect(screen.queryByTestId('area-confidenceLow')).not.toBeInTheDocument()
  })

  it('displays the lowest price information', () => {
    render(<ForecastChart forecast={mockForecast} />)

    // Hour 3 has price 0.10 which is the lowest
    // The text is split across child elements, so we use a function matcher
    const lowestSection = screen.getByText((_content, element) => {
      return element?.tagName === 'DIV' &&
        element?.classList.contains('text-sm') &&
        element?.textContent?.includes('$0.10') || false
    })
    expect(lowestSection).toBeInTheDocument()
  })

  it('shows forecast legend label', () => {
    render(<ForecastChart forecast={mockForecast} />)

    expect(screen.getByText('Forecast')).toBeInTheDocument()
  })

  it('shows confidence interval legend when showConfidence is true', () => {
    render(<ForecastChart forecast={mockForecast} showConfidence={true} />)

    expect(screen.getByText('Confidence interval')).toBeInTheDocument()
  })

  it('hides confidence interval legend when showConfidence is false', () => {
    render(<ForecastChart forecast={mockForecast} showConfidence={false} />)

    expect(screen.queryByText('Confidence interval')).not.toBeInTheDocument()
  })

  it('shows current price legend when currentPrice is provided', () => {
    render(<ForecastChart forecast={mockForecast} currentPrice={0.13} />)

    expect(screen.getByText('Current price')).toBeInTheDocument()
  })

  it('hides current price legend when no currentPrice', () => {
    render(<ForecastChart forecast={mockForecast} />)

    expect(screen.queryByText('Current price')).not.toBeInTheDocument()
  })

  it('accepts className prop for custom styling', () => {
    const { container } = render(
      <ForecastChart forecast={mockForecast} className="custom-class" />
    )

    expect(container.firstChild).toHaveClass('custom-class')
  })

  it('handles backend object format for forecast data', () => {
    const backendData = {
      prices: [
        { price_per_kwh: 0.12, timestamp: '2026-02-22T01:00:00Z' },
        { price_per_kwh: 0.15, timestamp: '2026-02-22T02:00:00Z' },
      ],
      confidence: 0.85,
    }

    render(<ForecastChart forecast={backendData} />)

    expect(screen.getByText('24-Hour Forecast')).toBeInTheDocument()
    expect(screen.getByTestId('area-chart')).toBeInTheDocument()
  })
})
