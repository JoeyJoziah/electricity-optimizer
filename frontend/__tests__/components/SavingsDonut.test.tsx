import { render, screen } from '@testing-library/react'
import { SavingsDonut } from '@/components/charts/SavingsDonut'
import '@testing-library/jest-dom'

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

  it('displays total savings in the center', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    expect(screen.getByText(/350/)).toBeInTheDocument()
  })

  it('shows savings breakdown by category', () => {
    render(<SavingsDonut data={mockSavingsData} showLegend />)

    expect(screen.getByText('Load Shifting')).toBeInTheDocument()
    expect(screen.getByText('Optimal Scheduling')).toBeInTheDocument()
    expect(screen.getByText('Price Alerts')).toBeInTheDocument()
  })

  it('displays percentages in legend', () => {
    render(<SavingsDonut data={mockSavingsData} showLegend />)

    expect(screen.getByText(/42\.86%/)).toBeInTheDocument()
    expect(screen.getByText(/34\.29%/)).toBeInTheDocument()
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

  it('formats currency correctly', () => {
    render(<SavingsDonut data={mockSavingsData} currency="USD" />)

    expect(screen.getByText(/\$350/)).toBeInTheDocument()
  })

  it('shows period label', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    expect(screen.getByText(/this month/i)).toBeInTheDocument()
  })

  it('supports different periods', () => {
    const yearlyData = { ...mockSavingsData, period: 'year' as const }

    render(<SavingsDonut data={yearlyData} />)

    expect(screen.getByText(/this year/i)).toBeInTheDocument()
  })

  it('uses correct colors for categories', () => {
    render(<SavingsDonut data={mockSavingsData} showLegend />)

    // Check that legend items have color indicators
    const legendItems = screen.getAllByTestId('legend-item')
    expect(legendItems).toHaveLength(3)
  })

  it('is accessible with ARIA labels', () => {
    render(<SavingsDonut data={mockSavingsData} />)

    const chart = screen.getByRole('img', { name: /savings chart/i })
    expect(chart).toHaveAttribute('aria-label')
  })
})
