import React from 'react'
import { render, screen } from '@testing-library/react'
import { SavingsDonut } from '@/components/charts/SavingsDonut'
import '@testing-library/jest-dom'

// Mock recharts to avoid jsdom SVG/canvas dimension warnings from ResponsiveContainer
jest.mock('recharts', () => {
  const MockResponsiveContainer = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  )
  const MockPieChart = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pie-chart">{children}</div>
  )
  const MockPie = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pie">{children}</div>
  )
  const MockCell = ({ fill }: { fill: string }) => (
    <div data-testid="cell" data-fill={fill} />
  )
  const MockTooltip = () => <div data-testid="tooltip" />

  return {
    ResponsiveContainer: MockResponsiveContainer,
    PieChart: MockPieChart,
    Pie: MockPie,
    Cell: MockCell,
    Tooltip: MockTooltip,
  }
})

jest.mock('@/lib/utils/format', () => ({
  formatCurrency: (amount: number, _currency?: string) => `$${amount.toFixed(2)}`,
}))

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

const mockSavingsData = {
  totalSavings: 350,
  breakdown: [
    { category: 'Load Shifting', amount: 150, percentage: 42.86 },
    { category: 'Optimal Scheduling', amount: 120, percentage: 34.29 },
    { category: 'Price Alerts', amount: 80, percentage: 22.85 },
  ],
  period: 'month' as const,
}

describe('SavingsDonut', () => {
  it('renders the donut chart', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    expect(screen.getByRole('img', { name: /savings chart/i })).toBeInTheDocument()
  })

  it('renders a PieChart with a ResponsiveContainer when there are savings', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    expect(screen.getByTestId('pie-chart')).toBeInTheDocument()
    expect(screen.getByTestId('pie')).toBeInTheDocument()
  })

  it('displays total savings in the center', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    expect(screen.getByText(/350/)).toBeInTheDocument()
  })

  it('formats total savings with currency symbol', () => {
    render(<SavingsDonut data={mockSavingsData} currency="USD" />)

    expect(screen.getByText(/\$350/)).toBeInTheDocument()
  })

  it('shows period label in the center', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    expect(screen.getByText(/this month/i)).toBeInTheDocument()
  })

  it('shows savings breakdown by category when showLegend is true', () => {
    render(<SavingsDonut data={mockSavingsData} showLegend />)

    expect(screen.getByText('Load Shifting')).toBeInTheDocument()
    expect(screen.getByText('Optimal Scheduling')).toBeInTheDocument()
    expect(screen.getByText('Price Alerts')).toBeInTheDocument()
  })

  it('does not show legend items when showLegend is false', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    expect(screen.queryByTestId('legend-item')).not.toBeInTheDocument()
  })

  it('displays percentages in legend', () => {
    render(<SavingsDonut data={mockSavingsData} showLegend />)

    expect(screen.getByText(/42\.86%/)).toBeInTheDocument()
    expect(screen.getByText(/34\.29%/)).toBeInTheDocument()
  })

  it('displays formatted amounts in legend', () => {
    render(<SavingsDonut data={mockSavingsData} showLegend />)

    // Each category amount should appear formatted
    expect(screen.getByText('$150.00')).toBeInTheDocument()
    expect(screen.getByText('$120.00')).toBeInTheDocument()
    expect(screen.getByText('$80.00')).toBeInTheDocument()
  })

  it('uses correct colors for categories in legend', () => {
    render(<SavingsDonut data={mockSavingsData} showLegend />)

    // Check that all legend items are rendered
    const legendItems = screen.getAllByTestId('legend-item')
    expect(legendItems).toHaveLength(3)
  })

  it('renders one Cell per breakdown category', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    const cells = screen.getAllByTestId('cell')
    expect(cells).toHaveLength(mockSavingsData.breakdown.length)
  })

  it('handles empty savings gracefully', () => {
    const emptyData = {
      totalSavings: 0,
      breakdown: [],
      period: 'month' as const,
    }

    render(<SavingsDonut data={emptyData} />)

    expect(screen.getByText(/no savings yet/i)).toBeInTheDocument()
  })

  it('does not render the pie chart in the empty state', () => {
    const emptyData = {
      totalSavings: 0,
      breakdown: [],
      period: 'month' as const,
    }

    render(<SavingsDonut data={emptyData} />)

    expect(screen.queryByTestId('responsive-container')).not.toBeInTheDocument()
  })

  it('shows period label in empty state', () => {
    const emptyData = {
      totalSavings: 0,
      breakdown: [],
      period: 'month' as const,
    }

    render(<SavingsDonut data={emptyData} />)

    expect(screen.getByText(/this month/i)).toBeInTheDocument()
  })

  it('renders empty state when breakdown is non-empty but totalSavings is 0', () => {
    const zeroWithBreakdown = {
      totalSavings: 0,
      breakdown: [{ category: 'Load Shifting', amount: 0, percentage: 0 }],
      period: 'week' as const,
    }

    render(<SavingsDonut data={zeroWithBreakdown} />)

    expect(screen.getByText(/no savings yet/i)).toBeInTheDocument()
  })

  it('supports the "day" period label', () => {
    const dailyData = { ...mockSavingsData, period: 'day' as const }

    render(<SavingsDonut data={dailyData} />)

    expect(screen.getByText(/today/i)).toBeInTheDocument()
  })

  it('supports the "week" period label', () => {
    const weeklyData = { ...mockSavingsData, period: 'week' as const }

    render(<SavingsDonut data={weeklyData} />)

    expect(screen.getByText(/this week/i)).toBeInTheDocument()
  })

  it('supports the "year" period label', () => {
    const yearlyData = { ...mockSavingsData, period: 'year' as const }

    render(<SavingsDonut data={yearlyData} />)

    expect(screen.getByText(/this year/i)).toBeInTheDocument()
  })

  it('is accessible with ARIA labels', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    const chart = screen.getByRole('img', { name: /savings chart/i })
    expect(chart).toHaveAttribute('aria-label')
  })

  it('applies custom className', () => {
    const { container } = render(
      <SavingsDonut data={mockSavingsData} className="custom-donut" />
    )

    expect(container.firstChild).toHaveClass('custom-donut')
  })

  it('applies custom className in empty state', () => {
    const emptyData = {
      totalSavings: 0,
      breakdown: [],
      period: 'month' as const,
    }

    const { container } = render(
      <SavingsDonut data={emptyData} className="custom-empty" />
    )

    expect(container.firstChild).toHaveClass('custom-empty')
  })

  it('cycles through COLORS array for more than 6 categories', () => {
    const manyCategories = {
      totalSavings: 700,
      breakdown: Array.from({ length: 7 }, (_, i) => ({
        category: `Category ${i + 1}`,
        amount: 100,
        percentage: 100 / 7,
      })),
      period: 'month' as const,
    }

    render(<SavingsDonut data={manyCategories} showLegend />)

    const legendItems = screen.getAllByTestId('legend-item')
    expect(legendItems).toHaveLength(7)
  })
})
