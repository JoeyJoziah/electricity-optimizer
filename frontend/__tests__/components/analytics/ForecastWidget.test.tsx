import { render, screen } from '@testing-library/react'
import { ForecastWidget } from '@/components/analytics/ForecastWidget'
import '@testing-library/jest-dom'

const mockUseForecast = jest.fn()
const mockUseForecastTypes = jest.fn()

jest.mock('@/lib/hooks/useForecast', () => ({
  useForecast: (...args: unknown[]) => mockUseForecast(...args),
  useForecastTypes: () => mockUseForecastTypes(),
}))

const mockForecastData = {
  utility_type: 'electricity',
  state: 'CT',
  unit: '$/kWh',
  current_rate: 0.15,
  forecasted_rate: 0.16,
  horizon_days: 30,
  trend: 'increasing' as const,
  percent_change: 6.67,
  confidence: 0.85,
  model: 'trend_extrapolation_v1',
  data_points: 30,
  r_squared: 0.92,
  generated_at: '2026-03-11T00:00:00Z',
}

describe('ForecastWidget', () => {
  beforeEach(() => {
    mockUseForecast.mockReset()
    mockUseForecastTypes.mockReset()
    mockUseForecastTypes.mockReturnValue({
      data: { supported_types: ['electricity', 'natural_gas', 'heating_oil', 'propane'] },
    })
  })

  it('shows loading state', () => {
    mockUseForecast.mockReturnValue({ data: null, isLoading: true, error: null })
    const { container } = render(<ForecastWidget state="CT" />)
    expect(screen.getByText('Rate Forecast')).toBeInTheDocument()
    expect(screen.getByText(/Loading forecast/)).toBeInTheDocument()
  })

  it('shows error state', () => {
    mockUseForecast.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('API error'),
    })
    render(<ForecastWidget state="CT" />)
    expect(screen.getByText(/API error/)).toBeInTheDocument()
  })

  it('renders forecast data with trend', () => {
    mockUseForecast.mockReturnValue({
      data: mockForecastData,
      isLoading: false,
      error: null,
    })
    render(<ForecastWidget state="CT" />)
    expect(screen.getByText('Rate Forecast')).toBeInTheDocument()
    expect(screen.getByText(/0\.15/)).toBeInTheDocument()
    expect(screen.getByText(/0\.16/)).toBeInTheDocument()
  })

  it('renders utility type selector', () => {
    mockUseForecast.mockReturnValue({ data: null, isLoading: false, error: null })
    render(<ForecastWidget state="CT" />)
    // The component has a select for utility type
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThanOrEqual(1)
  })
})
