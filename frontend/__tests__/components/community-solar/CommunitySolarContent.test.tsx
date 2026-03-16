import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// --- Mocks ---

let mockRegion: string | null = 'us_ct'

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (s: { region: string | null }) => unknown) =>
    selector({ region: mockRegion }),
}))

const mockPrograms = {
  count: 2,
  programs: [
    {
      id: 'prog-1',
      program_name: 'SunShare CT',
      provider: 'GreenPower Inc',
      enrollment_status: 'open',
      savings_percent: 15,
      description: 'Community solar program for CT residents',
      capacity_kw: 500,
      spots_available: 25,
      contract_months: 24,
      min_bill_amount: 50,
      enrollment_url: 'https://example.com/enroll',
      state: 'CT',
    },
    {
      id: 'prog-2',
      program_name: 'WaitList Solar',
      provider: 'SolarCo',
      enrollment_status: 'waitlist',
      savings_percent: 10,
      description: null,
      capacity_kw: null,
      spots_available: null,
      contract_months: null,
      min_bill_amount: null,
      enrollment_url: 'https://example.com/waitlist',
      state: 'CT',
    },
  ],
}

const mockStates = {
  total_states: 3,
  states: [
    { state: 'CT', program_count: 5 },
    { state: 'NY', program_count: 8 },
    { state: 'MA', program_count: 3 },
  ],
}

let mockProgramsLoading = false
let mockStatesData: typeof mockStates | undefined = mockStates

jest.mock('@/lib/hooks/useCommunitySolar', () => ({
  useCommunitySolarPrograms: () => ({
    data: mockProgramsLoading ? undefined : mockPrograms,
    isLoading: mockProgramsLoading,
  }),
  useCommunitySolarStates: () => ({
    data: mockStatesData,
  }),
}))

jest.mock('@/components/community-solar/SavingsCalculator', () => ({
  CommunitySolarService: () => (
    <div data-testid="savings-calculator">Savings Calculator</div>
  ),
}))

import CommunitySolarContent from '@/components/community-solar/CommunitySolarContent'

describe('CommunitySolarContent', () => {
  beforeEach(() => {
    mockRegion = 'us_ct'
    mockProgramsLoading = false
    mockStatesData = mockStates
    jest.clearAllMocks()
  })

  it('renders page heading', () => {
    render(<CommunitySolarContent />)

    expect(screen.getByText('Community Solar')).toBeInTheDocument()
    expect(
      screen.getByText(/Subscribe to a local solar farm/)
    ).toBeInTheDocument()
  })

  it('renders "no region set" message when region is null', () => {
    mockRegion = null

    render(<CommunitySolarContent />)

    expect(screen.getByText('No region set')).toBeInTheDocument()
    expect(
      screen.getByText(/Set your region in Settings/)
    ).toBeInTheDocument()
  })

  it('renders savings calculator', () => {
    render(<CommunitySolarContent />)

    expect(screen.getByTestId('savings-calculator')).toBeInTheDocument()
  })

  it('renders state coverage section', () => {
    render(<CommunitySolarContent />)

    expect(screen.getByText('Available in 3 States')).toBeInTheDocument()
    expect(screen.getByText('CT (5)')).toBeInTheDocument()
    expect(screen.getByText('NY (8)')).toBeInTheDocument()
    expect(screen.getByText('MA (3)')).toBeInTheDocument()
  })

  it('highlights current state in state coverage', () => {
    render(<CommunitySolarContent />)

    const ctBadge = screen.getByText('CT (5)')
    expect(ctBadge.className).toContain('bg-primary-100')
  })

  it('renders filter buttons and enrollment badges', () => {
    render(<CommunitySolarContent />)

    // "All" only appears once as a filter
    expect(screen.getByText('All')).toBeInTheDocument()
    // "Open" appears as filter button + enrollment badge
    const openElements = screen.getAllByText('Open')
    expect(openElements.length).toBeGreaterThanOrEqual(2)
    // "Waitlist" appears as filter button + enrollment badge
    const waitlistElements = screen.getAllByText('Waitlist')
    expect(waitlistElements.length).toBeGreaterThanOrEqual(2)
  })

  it('renders program cards', () => {
    render(<CommunitySolarContent />)

    expect(screen.getByText('SunShare CT')).toBeInTheDocument()
    expect(screen.getByText('by GreenPower Inc')).toBeInTheDocument()
    expect(screen.getByText('15%')).toBeInTheDocument()
    // Both programs show "savings" text
    const savingsLabels = screen.getAllByText('savings')
    expect(savingsLabels.length).toBe(2)
  })

  it('renders program details', () => {
    render(<CommunitySolarContent />)

    expect(screen.getByText(/500/)).toBeInTheDocument()
    expect(screen.getByText('25 spots available')).toBeInTheDocument()
    expect(screen.getByText('24 month contract')).toBeInTheDocument()
    expect(screen.getByText('Min bill: $50')).toBeInTheDocument()
  })

  it('renders enrollment CTA for open programs', () => {
    render(<CommunitySolarContent />)

    expect(screen.getByText('Enroll Now')).toBeInTheDocument()
    expect(screen.getByText('Join Waitlist')).toBeInTheDocument()
  })

  it('shows loading skeletons when loading', () => {
    mockProgramsLoading = true

    const { container } = render(<CommunitySolarContent />)

    const pulsingElements = container.querySelectorAll('.animate-pulse')
    expect(pulsingElements.length).toBeGreaterThan(0)
  })

  it('shows empty state when no programs found', () => {
    const origMock = jest.requireMock('@/lib/hooks/useCommunitySolar')
    const origFn = origMock.useCommunitySolarPrograms
    origMock.useCommunitySolarPrograms = () => ({
      data: { count: 0, programs: [] },
      isLoading: false,
    })

    render(<CommunitySolarContent />)

    expect(
      screen.getByText(/No community solar programs found/)
    ).toBeInTheDocument()

    origMock.useCommunitySolarPrograms = origFn
  })

  it('hides state coverage when no states data', () => {
    mockStatesData = undefined

    render(<CommunitySolarContent />)

    expect(screen.queryByText(/Available in/)).not.toBeInTheDocument()
  })
})
