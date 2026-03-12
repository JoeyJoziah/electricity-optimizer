import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CCAInfo } from '@/components/cca/CCAInfo'
import '@testing-library/jest-dom'

const mockUseCCAInfo = jest.fn()
jest.mock('@/lib/hooks/useCCA', () => ({
  useCCAInfo: (...args: unknown[]) => mockUseCCAInfo(...args),
}))

const mockProgram = {
  id: 'cca-1',
  program_name: 'San Jose Clean Energy',
  provider: 'City of San Jose',
  municipality: 'San Jose',
  state: 'CA',
  rate_vs_default_pct: -5,
  generation_mix: { solar: 40, wind: 30, hydro: 20, other: 10 },
  program_url: 'https://sanjosecleanenergy.org',
  opt_out_url: 'https://sanjosecleanenergy.org/opt-out',
  status: 'active',
}

describe('CCAInfo', () => {
  beforeEach(() => {
    mockUseCCAInfo.mockReset()
  })

  it('shows loading skeleton while fetching', () => {
    mockUseCCAInfo.mockReturnValue({ data: null, isLoading: true, error: null })
    const { container } = render(<CCAInfo ccaId="cca-1" />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('returns null on error', () => {
    mockUseCCAInfo.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') })
    const { container } = render(<CCAInfo ccaId="cca-1" />)
    expect(container.firstChild).toBeNull()
  })

  it('renders program name and provider', () => {
    mockUseCCAInfo.mockReturnValue({ data: mockProgram, isLoading: false, error: null })
    render(<CCAInfo ccaId="cca-1" />)

    expect(screen.getByText('San Jose Clean Energy')).toBeInTheDocument()
    expect(screen.getByText(/City of San Jose/)).toBeInTheDocument()
    expect(screen.getByText(/San Jose, CA/)).toBeInTheDocument()
  })

  it('shows rate badge for cheaper CCA', () => {
    mockUseCCAInfo.mockReturnValue({ data: mockProgram, isLoading: false, error: null })
    render(<CCAInfo ccaId="cca-1" />)

    expect(screen.getByText('5% below default rate')).toBeInTheDocument()
  })

  it('shows rate badge for more expensive CCA', () => {
    mockUseCCAInfo.mockReturnValue({
      data: { ...mockProgram, rate_vs_default_pct: 3 },
      isLoading: false,
      error: null,
    })
    render(<CCAInfo ccaId="cca-1" />)

    expect(screen.getByText('3% above default rate')).toBeInTheDocument()
  })

  it('shows same-rate badge when rate is zero', () => {
    mockUseCCAInfo.mockReturnValue({
      data: { ...mockProgram, rate_vs_default_pct: 0 },
      isLoading: false,
      error: null,
    })
    render(<CCAInfo ccaId="cca-1" />)

    expect(screen.getByText('Same as default rate')).toBeInTheDocument()
  })

  it('renders generation mix bar and legend', () => {
    mockUseCCAInfo.mockReturnValue({ data: mockProgram, isLoading: false, error: null })
    render(<CCAInfo ccaId="cca-1" />)

    expect(screen.getByText('Generation Mix')).toBeInTheDocument()
    expect(screen.getByText('solar')).toBeInTheDocument()
    expect(screen.getByText('wind')).toBeInTheDocument()
    expect(screen.getByText('hydro')).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()
    expect(screen.getByText('30%')).toBeInTheDocument()
  })

  it('hides generation mix when null', () => {
    mockUseCCAInfo.mockReturnValue({
      data: { ...mockProgram, generation_mix: null },
      isLoading: false,
      error: null,
    })
    render(<CCAInfo ccaId="cca-1" />)

    expect(screen.queryByText('Generation Mix')).not.toBeInTheDocument()
  })

  it('renders program and opt-out links', () => {
    mockUseCCAInfo.mockReturnValue({ data: mockProgram, isLoading: false, error: null })
    render(<CCAInfo ccaId="cca-1" />)

    const programLink = screen.getByText('Program Website')
    expect(programLink).toHaveAttribute('href', 'https://sanjosecleanenergy.org')

    const optOutLink = screen.getByText('Opt-Out Information')
    expect(optOutLink).toHaveAttribute('href', 'https://sanjosecleanenergy.org/opt-out')
  })

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup()
    const onClose = jest.fn()
    mockUseCCAInfo.mockReturnValue({ data: mockProgram, isLoading: false, error: null })
    render(<CCAInfo ccaId="cca-1" onClose={onClose} />)

    await user.click(screen.getByLabelText('Close CCA info'))
    expect(onClose).toHaveBeenCalled()
  })

  it('hides close button when onClose not provided', () => {
    mockUseCCAInfo.mockReturnValue({ data: mockProgram, isLoading: false, error: null })
    render(<CCAInfo ccaId="cca-1" />)

    expect(screen.queryByLabelText('Close CCA info')).not.toBeInTheDocument()
  })
})
