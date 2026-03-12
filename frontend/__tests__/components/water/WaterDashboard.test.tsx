import { render, screen, fireEvent } from '@testing-library/react'
import { WaterDashboard } from '@/components/water/WaterDashboard'
import '@testing-library/jest-dom'

// Mock child components
jest.mock('@/components/water/WaterRateBenchmark', () => ({
  WaterRateBenchmark: ({ state }: { state: string }) => (
    <div data-testid="water-benchmark">Benchmark: {state}</div>
  ),
}))
jest.mock('@/components/water/WaterTierCalculator', () => ({
  WaterTierCalculator: ({ state }: { state: string }) => (
    <div data-testid="water-calculator">Calculator: {state}</div>
  ),
}))
jest.mock('@/components/water/ConservationTips', () => ({
  ConservationTips: () => <div data-testid="conservation-tips">Tips</div>,
}))

describe('WaterDashboard', () => {
  it('renders info banner', () => {
    render(<WaterDashboard />)
    expect(screen.getByText('Water Rate Benchmarking')).toBeInTheDocument()
    expect(screen.getByText(/geographic monopolies/)).toBeInTheDocument()
  })

  it('renders state selector', () => {
    render(<WaterDashboard />)
    expect(screen.getByLabelText('Select State')).toBeInTheDocument()
  })

  it('always shows conservation tips', () => {
    render(<WaterDashboard />)
    expect(screen.getByTestId('conservation-tips')).toBeInTheDocument()
  })

  it('does not show benchmark or calculator without state selection', () => {
    render(<WaterDashboard />)
    expect(screen.queryByTestId('water-benchmark')).not.toBeInTheDocument()
    expect(screen.queryByTestId('water-calculator')).not.toBeInTheDocument()
  })

  it('shows benchmark and calculator when state selected', () => {
    render(<WaterDashboard />)
    fireEvent.change(screen.getByLabelText('Select State'), { target: { value: 'NY' } })

    expect(screen.getByTestId('water-benchmark')).toBeInTheDocument()
    expect(screen.getByText('Benchmark: NY')).toBeInTheDocument()
    expect(screen.getByTestId('water-calculator')).toBeInTheDocument()
    expect(screen.getByText('Calculator: NY')).toBeInTheDocument()
  })

  it('has all 50 states plus DC in selector', () => {
    render(<WaterDashboard />)
    const select = screen.getByLabelText('Select State') as HTMLSelectElement
    // 51 state options + 1 "Choose a state..." placeholder = 52
    expect(select.options.length).toBe(52)
  })
})
