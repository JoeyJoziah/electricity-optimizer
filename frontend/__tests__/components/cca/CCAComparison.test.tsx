import { render, screen } from '@testing-library/react'
import { CCAComparison } from '@/components/cca/CCAComparison'
import '@testing-library/jest-dom'

const mockUseCCACompare = jest.fn()
jest.mock('@/lib/hooks/useCCA', () => ({
  useCCACompare: (...args: unknown[]) => mockUseCCACompare(...args),
}))

const mockCheaperData = {
  cca_id: 'cca-1',
  program_name: 'San Jose Clean Energy',
  provider: 'City of San Jose',
  default_rate: 0.2,
  cca_rate: 0.19,
  rate_difference_pct: -5,
  savings_per_kwh: 0.01,
  estimated_monthly_savings: 9.0,
  is_cheaper: true,
}

const mockExpensiveData = {
  ...mockCheaperData,
  cca_rate: 0.206,
  rate_difference_pct: 3,
  savings_per_kwh: -0.006,
  estimated_monthly_savings: -5.4,
  is_cheaper: false,
}

describe('CCAComparison', () => {
  beforeEach(() => {
    mockUseCCACompare.mockReset()
  })

  it('shows loading skeleton while fetching', () => {
    mockUseCCACompare.mockReturnValue({ data: null, isLoading: true, error: null })
    const { container } = render(<CCAComparison ccaId="cca-1" defaultRate={0.2} />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('returns null on error', () => {
    mockUseCCACompare.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') })
    const { container } = render(<CCAComparison ccaId="cca-1" defaultRate={0.2} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders rate comparison header', () => {
    mockUseCCACompare.mockReturnValue({ data: mockCheaperData, isLoading: false, error: null })
    render(<CCAComparison ccaId="cca-1" defaultRate={0.2} />)

    expect(screen.getByText('Rate Comparison')).toBeInTheDocument()
    expect(screen.getByText(/San Jose Clean Energy/)).toBeInTheDocument()
  })

  it('displays both rates', () => {
    mockUseCCACompare.mockReturnValue({ data: mockCheaperData, isLoading: false, error: null })
    render(<CCAComparison ccaId="cca-1" defaultRate={0.2} />)

    expect(screen.getByText('$0.2000/kWh')).toBeInTheDocument()
    expect(screen.getByText('$0.1900/kWh')).toBeInTheDocument()
  })

  it('shows savings message when CCA is cheaper', () => {
    mockUseCCACompare.mockReturnValue({ data: mockCheaperData, isLoading: false, error: null })
    render(<CCAComparison ccaId="cca-1" defaultRate={0.2} />)

    expect(screen.getByText(/Saving ~\$9\.00\/month/)).toBeInTheDocument()
    expect(screen.getByText(/5% less/)).toBeInTheDocument()
  })

  it('shows cost increase message when CCA is more expensive', () => {
    mockUseCCACompare.mockReturnValue({ data: mockExpensiveData, isLoading: false, error: null })
    render(<CCAComparison ccaId="cca-1" defaultRate={0.2} />)

    expect(screen.getByText(/Costing ~\$5\.40\/month more/)).toBeInTheDocument()
    expect(screen.getByText(/3% higher/)).toBeInTheDocument()
  })

  it('applies success color when CCA is cheaper', () => {
    mockUseCCACompare.mockReturnValue({ data: mockCheaperData, isLoading: false, error: null })
    render(<CCAComparison ccaId="cca-1" defaultRate={0.2} />)

    const ccaRate = screen.getByText('$0.1900/kWh')
    expect(ccaRate.className).toContain('text-success-600')
  })

  it('applies danger color when CCA is more expensive', () => {
    mockUseCCACompare.mockReturnValue({ data: mockExpensiveData, isLoading: false, error: null })
    render(<CCAComparison ccaId="cca-1" defaultRate={0.2} />)

    const ccaRate = screen.getByText('$0.2060/kWh')
    expect(ccaRate.className).toContain('text-danger-600')
  })
})
