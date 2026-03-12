import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CCAAlert } from '@/components/cca/CCAAlert'
import '@testing-library/jest-dom'

// Mock hooks
const mockUseCCADetect = jest.fn()
jest.mock('@/lib/hooks/useCCA', () => ({
  useCCADetect: (...args: unknown[]) => mockUseCCADetect(...args),
}))

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (s: { region: string }) => string) =>
    selector({ region: 'us-ca' }),
}))

const mockProgram = {
  id: 'cca-1',
  program_name: 'San Jose Clean Energy',
  provider: 'City of San Jose',
  municipality: 'San Jose',
  state: 'CA',
  rate_vs_default_pct: -5,
  program_url: 'https://sanjosecleanenergy.org',
  opt_out_url: null,
  status: 'active',
  generation_mix: null,
}

describe('CCAAlert', () => {
  beforeEach(() => {
    mockUseCCADetect.mockReset()
  })

  it('returns null while loading', () => {
    mockUseCCADetect.mockReturnValue({ data: null, isLoading: true })
    const { container } = render(<CCAAlert />)
    expect(container.firstChild).toBeNull()
  })

  it('returns null when not in a CCA area', () => {
    mockUseCCADetect.mockReturnValue({
      data: { in_cca: false, program: null },
      isLoading: false,
    })
    const { container } = render(<CCAAlert />)
    expect(container.firstChild).toBeNull()
  })

  it('renders CCA alert when user is in a CCA area', () => {
    mockUseCCADetect.mockReturnValue({
      data: { in_cca: true, program: mockProgram },
      isLoading: false,
    })
    render(<CCAAlert />)

    expect(screen.getByText("You're in a CCA Program")).toBeInTheDocument()
    expect(screen.getByText(/San Jose Clean Energy/)).toBeInTheDocument()
    expect(screen.getByText(/City of San Jose/)).toBeInTheDocument()
    expect(screen.getByText(/San Jose, CA/)).toBeInTheDocument()
  })

  it('shows savings percentage when rate is lower', () => {
    mockUseCCADetect.mockReturnValue({
      data: { in_cca: true, program: mockProgram },
      isLoading: false,
    })
    render(<CCAAlert />)

    expect(screen.getByText('5% lower than default utility rate')).toBeInTheDocument()
  })

  it('does not show savings when rate is higher', () => {
    mockUseCCADetect.mockReturnValue({
      data: {
        in_cca: true,
        program: { ...mockProgram, rate_vs_default_pct: 3 },
      },
      isLoading: false,
    })
    render(<CCAAlert />)

    expect(screen.queryByText(/lower than default/)).not.toBeInTheDocument()
  })

  it('shows program website link when available', () => {
    mockUseCCADetect.mockReturnValue({
      data: { in_cca: true, program: mockProgram },
      isLoading: false,
    })
    render(<CCAAlert />)

    const link = screen.getByText('Program Website')
    expect(link).toHaveAttribute('href', 'https://sanjosecleanenergy.org')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('calls onViewDetails when View Details is clicked', async () => {
    const user = userEvent.setup()
    const onViewDetails = jest.fn()
    mockUseCCADetect.mockReturnValue({
      data: { in_cca: true, program: mockProgram },
      isLoading: false,
    })
    render(<CCAAlert onViewDetails={onViewDetails} />)

    await user.click(screen.getByText('View Details'))
    expect(onViewDetails).toHaveBeenCalledWith('cca-1')
  })

  it('calls onDismiss when dismiss button is clicked', async () => {
    const user = userEvent.setup()
    const onDismiss = jest.fn()
    mockUseCCADetect.mockReturnValue({
      data: { in_cca: true, program: mockProgram },
      isLoading: false,
    })
    render(<CCAAlert onDismiss={onDismiss} />)

    await user.click(screen.getByLabelText('Dismiss CCA alert'))
    expect(onDismiss).toHaveBeenCalled()
  })

  it('hides dismiss button when onDismiss not provided', () => {
    mockUseCCADetect.mockReturnValue({
      data: { in_cca: true, program: mockProgram },
      isLoading: false,
    })
    render(<CCAAlert />)

    expect(screen.queryByLabelText('Dismiss CCA alert')).not.toBeInTheDocument()
  })
})
