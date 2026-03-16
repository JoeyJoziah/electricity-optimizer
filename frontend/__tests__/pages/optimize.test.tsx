import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'

// --- Store mock ---
const mockAppliances: { id: string; name: string; powerKw: number; typicalDurationHours: number; isFlexible: boolean; priority: string }[] = []
const mockAddAppliance = jest.fn((a) => mockAppliances.push(a))
const mockRemoveAppliance = jest.fn()
const mockUpdateAppliance = jest.fn()

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      region: 'us_ct',
      appliances: mockAppliances,
      addAppliance: mockAddAppliance,
      removeAppliance: mockRemoveAppliance,
      updateAppliance: mockUpdateAppliance,
    }),
}))

// --- Hook mocks ---
const mockRefetchSchedule = jest.fn()
const mockUseOptimalSchedule = jest.fn()
const mockUsePotentialSavings = jest.fn()

jest.mock('@/lib/hooks/useOptimization', () => ({
  useOptimalSchedule: (...args: unknown[]) => mockUseOptimalSchedule(...args),
  useSavedAppliances: jest.fn(() => ({ data: null })),
  useAppliances: jest.fn(() => ({ data: null })),
  useSaveAppliances: jest.fn(() => ({ mutate: jest.fn() })),
  usePotentialSavings: (...args: unknown[]) => mockUsePotentialSavings(...args),
}))

// --- Layout mock ---
jest.mock('@/components/layout/Header', () => ({
  Header: ({ title }: { title: string }) => <h1>{title}</h1>,
}))

// --- Chart mock ---
jest.mock('@/components/charts/ScheduleTimeline', () => ({
  ScheduleTimeline: () => <div data-testid="schedule-timeline">Timeline</div>,
}))

// --- Format utils mock ---
jest.mock('@/lib/utils/format', () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
  formatDuration: (h: number) => `${h}h`,
}))

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

import OptimizePage from '@/app/(app)/optimize/page'

describe('OptimizePage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Clear mock appliances array
    mockAppliances.length = 0

    mockUseOptimalSchedule.mockReturnValue({
      data: null,
      isLoading: false,
      refetch: mockRefetchSchedule,
    })
    mockUsePotentialSavings.mockReturnValue({ data: null })
  })

  it('renders the Load Optimization heading', () => {
    render(<OptimizePage />)
    expect(screen.getByRole('heading', { name: /load optimization/i })).toBeInTheDocument()
  })

  it('renders appliance count stat card showing 0', () => {
    render(<OptimizePage />)
    expect(screen.getByText('Appliances')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('renders savings stat cards with -- placeholders', () => {
    render(<OptimizePage />)
    expect(screen.getByText('Daily Savings')).toBeInTheDocument()
    expect(screen.getByText('Monthly Savings')).toBeInTheDocument()
    expect(screen.getByText('Annual Savings')).toBeInTheDocument()
    // All should show -- when no savings data
    const dashes = screen.getAllByText('--')
    expect(dashes.length).toBeGreaterThanOrEqual(3)
  })

  it('renders Your Appliances section', () => {
    render(<OptimizePage />)
    expect(screen.getByText('Your Appliances')).toBeInTheDocument()
  })

  it('shows empty state when no appliances', () => {
    render(<OptimizePage />)
    expect(screen.getByText(/no appliances added yet/i)).toBeInTheDocument()
  })

  it('renders Quick Add presets', () => {
    render(<OptimizePage />)
    expect(screen.getByRole('button', { name: /washing machine/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /dishwasher/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ev charger/i })).toBeInTheDocument()
  })

  it('renders custom add form inputs', () => {
    render(<OptimizePage />)
    expect(screen.getByPlaceholderText(/appliance name/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/power \(kw\)/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/duration \(hrs\)/i)).toBeInTheDocument()
  })

  it('renders Add Appliance button (disabled when name is empty)', () => {
    render(<OptimizePage />)
    const addButton = screen.getByRole('button', { name: /add appliance/i })
    expect(addButton).toBeDisabled()
  })

  it('enables Add Appliance button when name is entered', async () => {
    const user = userEvent.setup()
    render(<OptimizePage />)

    await user.type(screen.getByPlaceholderText(/appliance name/i), 'Tumble Dryer')

    expect(screen.getByRole('button', { name: /add appliance/i })).toBeEnabled()
  })

  it('calls addAppliance when Add Appliance button is clicked with a name', async () => {
    const user = userEvent.setup()
    render(<OptimizePage />)

    await user.type(screen.getByPlaceholderText(/appliance name/i), 'Dishwasher')
    await user.click(screen.getByRole('button', { name: /add appliance/i }))

    expect(mockAddAppliance).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Dishwasher',
    }))
  })

  it('calls addAppliance when a Quick Add preset is clicked', async () => {
    const user = userEvent.setup()
    render(<OptimizePage />)

    await user.click(screen.getByRole('button', { name: /washing machine/i }))

    expect(mockAddAppliance).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Washing Machine',
    }))
  })

  it('renders Optimize Your Schedule card', () => {
    render(<OptimizePage />)
    expect(screen.getByText(/optimize your schedule/i)).toBeInTheDocument()
  })

  it('renders Optimize Now button (disabled when no appliances)', () => {
    render(<OptimizePage />)
    expect(screen.getByRole('button', { name: /optimize now/i })).toBeDisabled()
  })

  it('shows "add appliances to start optimizing" empty state when no appliances and no schedule', () => {
    render(<OptimizePage />)
    expect(screen.getByText(/add appliances to start optimizing/i)).toBeInTheDocument()
  })

  it('shows loading skeleton when schedule is loading', () => {
    mockUseOptimalSchedule.mockReturnValue({
      data: null,
      isLoading: true,
      refetch: mockRefetchSchedule,
    })
    render(<OptimizePage />)

    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).not.toBeNull()
  })

  it('shows schedule results when schedules are returned', () => {
    mockUseOptimalSchedule.mockReturnValue({
      data: {
        schedules: [
          {
            applianceId: 'a1',
            applianceName: 'Washing Machine',
            scheduledStart: '2026-03-03T02:00:00Z',
            scheduledEnd: '2026-03-03T04:00:00Z',
            savings: 0.45,
            reason: 'Off-peak hours',
          },
        ],
        totalSavings: 0.45,
      },
      isLoading: false,
      refetch: mockRefetchSchedule,
    })
    render(<OptimizePage />)

    expect(screen.getByText('Optimized Schedule')).toBeInTheDocument()
    // Washing Machine also appears as Quick Add button — use getAllBy
    expect(screen.getAllByText('Washing Machine').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Off-peak hours')).toBeInTheDocument()
    expect(screen.getByTestId('schedule-timeline')).toBeInTheDocument()
  })

  it('shows total savings card when schedule data is available', () => {
    mockUseOptimalSchedule.mockReturnValue({
      data: {
        schedules: [
          {
            applianceId: 'a1',
            applianceName: 'EV Charger',
            scheduledStart: '2026-03-03T01:00:00Z',
            scheduledEnd: '2026-03-03T05:00:00Z',
            savings: 1.20,
            reason: 'Low rates overnight',
          },
        ],
        totalSavings: 1.20,
      },
      isLoading: false,
      refetch: mockRefetchSchedule,
    })
    render(<OptimizePage />)

    expect(screen.getByText(/total savings today/i)).toBeInTheDocument()
    expect(screen.getByText('$1.20')).toBeInTheDocument()
  })

  it('calls refetchSchedule when Optimize Now is clicked with appliances present', async () => {
    // Inject one appliance into the mock array
    mockAppliances.push({
      id: '1',
      name: 'Dryer',
      powerKw: 2.5,
      typicalDurationHours: 1,
      isFlexible: true,
      priority: 'low',
    })

    mockUseOptimalSchedule.mockReturnValue({
      data: null,
      isLoading: false,
      refetch: mockRefetchSchedule,
    })

    const user = userEvent.setup()
    render(<OptimizePage />)

    const optimizeBtn = screen.getByRole('button', { name: /optimize now/i })
    expect(optimizeBtn).toBeEnabled()

    await user.click(optimizeBtn)
    expect(mockRefetchSchedule).toHaveBeenCalledTimes(1)
  })
})
