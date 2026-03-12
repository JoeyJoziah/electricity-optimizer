import { render, screen } from '@testing-library/react'
import { OptimizationReport } from '@/components/analytics/OptimizationReport'
import '@testing-library/jest-dom'

const mockUseOptimizationReport = jest.fn()

jest.mock('@/lib/hooks/useReports', () => ({
  useOptimizationReport: (...args: unknown[]) => mockUseOptimizationReport(...args),
}))

const mockReport = {
  state: 'CT',
  generated_at: '2026-03-11T00:00:00Z',
  utilities: [
    {
      utility_type: 'electricity',
      unit: '$/kWh',
      current_rate: 0.15,
      monthly_consumption: 886,
      consumption_unit: 'kWh',
      monthly_cost: 132.9,
    },
  ],
  total_monthly_spend: 132.9,
  total_annual_spend: 1594.8,
  savings_opportunities: [
    {
      utility_type: 'electricity',
      action: 'Switch to cheapest supplier',
      monthly_savings: 15.0,
      annual_savings: 180.0,
      difficulty: 'easy',
    },
  ],
  total_potential_monthly_savings: 15.0,
  total_potential_annual_savings: 180.0,
  utility_count: 1,
}

describe('OptimizationReport', () => {
  beforeEach(() => {
    mockUseOptimizationReport.mockReset()
  })

  it('shows prompt when no state is provided', () => {
    mockUseOptimizationReport.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    })
    render(<OptimizationReport />)
    expect(screen.getByText(/Select a state/)).toBeInTheDocument()
  })

  it('shows loading state', () => {
    mockUseOptimizationReport.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    })
    render(<OptimizationReport state="CT" />)
    expect(screen.getByText(/Generating optimization report/)).toBeInTheDocument()
  })

  it('shows error state', () => {
    mockUseOptimizationReport.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Report error'),
    })
    render(<OptimizationReport state="CT" />)
    expect(screen.getByText(/Report error/)).toBeInTheDocument()
  })

  it('renders report with spend summary', () => {
    mockUseOptimizationReport.mockReturnValue({
      data: mockReport,
      isLoading: false,
      error: null,
    })
    render(<OptimizationReport state="CT" />)
    expect(screen.getByText('Spend Optimization Report')).toBeInTheDocument()
    expect(screen.getByText('$132.90')).toBeInTheDocument()
    expect(screen.getByText('$1594.80')).toBeInTheDocument()
  })

  it('renders savings opportunities', () => {
    mockUseOptimizationReport.mockReturnValue({
      data: mockReport,
      isLoading: false,
      error: null,
    })
    render(<OptimizationReport state="CT" />)
    expect(screen.getByText(/Switch to cheapest supplier/)).toBeInTheDocument()
    expect(screen.getByText(/Save \$15\.00\/mo/)).toBeInTheDocument()
  })

  it('renders utility breakdown', () => {
    mockUseOptimizationReport.mockReturnValue({
      data: mockReport,
      isLoading: false,
      error: null,
    })
    render(<OptimizationReport state="CT" />)
    expect(screen.getByText('Electricity')).toBeInTheDocument()
  })
})
