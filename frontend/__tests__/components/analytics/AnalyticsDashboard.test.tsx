import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AnalyticsDashboard } from '@/components/analytics/AnalyticsDashboard'
import '@testing-library/jest-dom'

jest.mock('@/components/analytics/ForecastWidget', () => ({
  ForecastWidget: ({ state }: { state: string }) => (
    <div data-testid="forecast-widget">Forecast: {state}</div>
  ),
}))
jest.mock('@/components/analytics/OptimizationReport', () => ({
  OptimizationReport: ({ state }: { state: string }) => (
    <div data-testid="optimization-report">Report: {state}</div>
  ),
}))
jest.mock('@/components/analytics/DataExport', () => ({
  DataExport: ({ state }: { state: string }) => (
    <div data-testid="data-export">Export: {state}</div>
  ),
}))

describe('AnalyticsDashboard', () => {
  it('renders state selector with default CT', () => {
    render(<AnalyticsDashboard />)
    const select = screen.getByLabelText('State') as HTMLSelectElement
    expect(select.value).toBe('CT')
  })

  it('renders all three child widgets', () => {
    render(<AnalyticsDashboard />)
    expect(screen.getByTestId('forecast-widget')).toBeInTheDocument()
    expect(screen.getByTestId('optimization-report')).toBeInTheDocument()
    expect(screen.getByTestId('data-export')).toBeInTheDocument()
  })

  it('passes selected state to child widgets', () => {
    render(<AnalyticsDashboard />)
    expect(screen.getByText('Forecast: CT')).toBeInTheDocument()
    expect(screen.getByText('Report: CT')).toBeInTheDocument()
    expect(screen.getByText('Export: CT')).toBeInTheDocument()
  })

  it('updates state when selector changes', async () => {
    const user = userEvent.setup()
    render(<AnalyticsDashboard />)
    const select = screen.getByLabelText('State')
    await user.selectOptions(select, 'NY')
    expect(screen.getByText('Forecast: NY')).toBeInTheDocument()
    expect(screen.getByText('Report: NY')).toBeInTheDocument()
    expect(screen.getByText('Export: NY')).toBeInTheDocument()
  })

  it('renders all 51 state options (50 states + DC)', () => {
    render(<AnalyticsDashboard />)
    const select = screen.getByLabelText('State') as HTMLSelectElement
    expect(select.options.length).toBe(51)
  })
})
