import { render, screen } from '@testing-library/react'
import { WaterRateBenchmark } from '@/components/water/WaterRateBenchmark'
import '@testing-library/jest-dom'

const mockUseWaterBenchmark = jest.fn()
jest.mock('@/lib/hooks/useWater', () => ({
  useWaterBenchmark: (...args: unknown[]) => mockUseWaterBenchmark(...args),
}))

const MOCK_BENCHMARK = {
  state: 'NY',
  municipalities: 2,
  usage_gallons: 5760,
  avg_monthly_cost: 45.50,
  min_monthly_cost: 38.00,
  max_monthly_cost: 53.00,
  rates: [
    { municipality: 'Buffalo', monthly_cost: 38.00, base_charge: 12.00 },
    { municipality: 'New York', monthly_cost: 53.00, base_charge: 15.50 },
  ],
}

describe('WaterRateBenchmark', () => {
  beforeEach(() => {
    mockUseWaterBenchmark.mockReset()
  })

  it('shows loading skeleton', () => {
    mockUseWaterBenchmark.mockReturnValue({ data: null, isLoading: true, error: null })
    const { container } = render(<WaterRateBenchmark state="NY" />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders nothing on error', () => {
    mockUseWaterBenchmark.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') })
    const { container } = render(<WaterRateBenchmark state="NY" />)
    expect(container.innerHTML).toBe('')
  })

  it('displays benchmark summary cards', () => {
    mockUseWaterBenchmark.mockReturnValue({ data: MOCK_BENCHMARK, isLoading: false, error: null })
    render(<WaterRateBenchmark state="NY" />)

    expect(screen.getByText('Water Rate Benchmark — NY')).toBeInTheDocument()
    expect(screen.getByText('$45.50')).toBeInTheDocument()
    expect(screen.getByText('$38.00')).toBeInTheDocument()
    expect(screen.getByText('$53.00')).toBeInTheDocument()
  })

  it('displays municipality breakdown', () => {
    mockUseWaterBenchmark.mockReturnValue({ data: MOCK_BENCHMARK, isLoading: false, error: null })
    render(<WaterRateBenchmark state="NY" />)

    expect(screen.getByText('New York')).toBeInTheDocument()
    expect(screen.getByText('Buffalo')).toBeInTheDocument()
    expect(screen.getByText('Municipality Comparison')).toBeInTheDocument()
  })

  it('shows usage info', () => {
    mockUseWaterBenchmark.mockReturnValue({ data: MOCK_BENCHMARK, isLoading: false, error: null })
    render(<WaterRateBenchmark state="NY" />)

    expect(screen.getByText(/5,760 gallons\/month/)).toBeInTheDocument()
    expect(screen.getByText(/2 municipalities/)).toBeInTheDocument()
  })
})
