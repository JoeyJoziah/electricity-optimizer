import { render, screen, waitFor } from '@testing-library/react'
import CommunitySolarPage from '@/app/(app)/community-solar/page'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import React from 'react'

// Mock settings store
jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      region: 'us_ny',
      utilityTypes: ['electricity', 'community_solar'],
      priceAlerts: [],
    }),
}))

// Mock API modules
const mockGetPrograms = jest.fn()
const mockGetSavings = jest.fn()
const mockGetStates = jest.fn()

jest.mock('@/lib/api/community-solar', () => ({
  getCommunitySolarPrograms: (...args: unknown[]) => mockGetPrograms(...args),
  getCommunitySolarSavings: (...args: unknown[]) => mockGetSavings(...args),
  getCommunitySolarProgram: jest.fn(),
  getCommunitySolarStates: (...args: unknown[]) => mockGetStates(...args),
}))

// Mock lucide-react icons used by community solar components
jest.mock('lucide-react', () => ({
  Sun: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-sun" {...props} />,
  ExternalLink: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-external" {...props} />,
  Users: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-users" {...props} />,
  MapPin: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-mappin" {...props} />,
  Calculator: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-calculator" {...props} />,
  DollarSign: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-dollar" {...props} />,
}))

const defaultProgramsResponse = {
  state: 'NY',
  count: 2,
  programs: [
    {
      id: '1',
      state: 'NY',
      program_name: 'NY Community Solar',
      provider: 'Nexamp',
      savings_percent: '10.00',
      capacity_kw: '5000.00',
      spots_available: 150,
      enrollment_url: 'https://www.nexamp.com/ny',
      enrollment_status: 'open',
      description: 'Save 10% on your electricity bill.',
      min_bill_amount: '50.00',
      contract_months: 12,
      updated_at: '2026-03-10T00:00:00Z',
    },
    {
      id: '2',
      state: 'NY',
      program_name: 'CleanChoice Solar NY',
      provider: 'CleanChoice Energy',
      savings_percent: '5.00',
      capacity_kw: '3000.00',
      spots_available: null,
      enrollment_url: 'https://cleanchoiceenergy.com',
      enrollment_status: 'waitlist',
      description: 'Join the waitlist for community solar.',
      min_bill_amount: '40.00',
      contract_months: null,
      updated_at: '2026-03-10T00:00:00Z',
    },
  ],
}

const defaultStatesResponse = {
  total_states: 3,
  states: [
    { state: 'NY', program_count: 2 },
    { state: 'MA', program_count: 2 },
    { state: 'MN', program_count: 1 },
  ],
}

describe('CommunitySolarPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })

    mockGetPrograms.mockResolvedValue(defaultProgramsResponse)
    mockGetStates.mockResolvedValue(defaultStatesResponse)
    mockGetSavings.mockResolvedValue({
      current_monthly_bill: '150.00',
      savings_percent: '10',
      monthly_savings: '15.00',
      annual_savings: '180.00',
      five_year_savings: '900.00',
      new_monthly_bill: '135.00',
    })
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('renders the page title', async () => {
    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Community Solar')).toBeInTheDocument()
    })
  })

  it('renders page description', async () => {
    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/no rooftop panels needed/i)).toBeInTheDocument()
    })
  })

  it('renders program cards', async () => {
    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('NY Community Solar')).toBeInTheDocument()
      expect(screen.getByText('CleanChoice Solar NY')).toBeInTheDocument()
    })
  })

  it('renders provider names', async () => {
    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('by Nexamp')).toBeInTheDocument()
      expect(screen.getByText('by CleanChoice Energy')).toBeInTheDocument()
    })
  })

  it('renders enrollment status badges', async () => {
    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Open')).toBeInTheDocument()
      expect(screen.getByText('Waitlist')).toBeInTheDocument()
    })
  })

  it('renders savings percentages', async () => {
    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('10.00%')).toBeInTheDocument()
      expect(screen.getByText('5.00%')).toBeInTheDocument()
    })
  })

  it('renders enrollment CTAs', async () => {
    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Enroll Now')).toBeInTheDocument()
      expect(screen.getByText('Join Waitlist')).toBeInTheDocument()
    })
  })

  it('renders savings calculator', async () => {
    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Savings Calculator')).toBeInTheDocument()
      expect(screen.getByLabelText(/Monthly Bill/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Savings \(%\)/)).toBeInTheDocument()
    })
  })

  it('renders state availability chips', async () => {
    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('NY (2)')).toBeInTheDocument()
      expect(screen.getByText('MA (2)')).toBeInTheDocument()
      expect(screen.getByText('MN (1)')).toBeInTheDocument()
    })
  })

  it('renders filter buttons', async () => {
    render(<CommunitySolarPage />, { wrapper })

    expect(screen.getByText('All')).toBeInTheDocument()
    // Multiple "Open" elements — filter button + enrollment badge
    expect(screen.getAllByText('Open').length).toBeGreaterThanOrEqual(1)
  })

  it('renders loading skeletons while data fetches', () => {
    mockGetPrograms.mockReturnValue(new Promise(() => {}))
    mockGetStates.mockReturnValue(new Promise(() => {}))

    render(<CommunitySolarPage />, { wrapper })

    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('handles empty programs', async () => {
    mockGetPrograms.mockResolvedValue({ state: 'NY', count: 0, programs: [] })

    render(<CommunitySolarPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/No community solar programs found/)).toBeInTheDocument()
    })
  })

  it('shows no-region message when region is null', () => {
    jest.spyOn(require('@/lib/store/settings'), 'useSettingsStore').mockImplementation(
      (selector: (state: Record<string, unknown>) => unknown) =>
        selector({ region: null, utilityTypes: [], priceAlerts: [] })
    )

    render(<CommunitySolarPage />, { wrapper })

    expect(screen.getByText('No region set')).toBeInTheDocument()
    expect(screen.getByText(/Set your region in Settings/)).toBeInTheDocument()
  })
})
