import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import React from 'react'

// ---------------------------------------------------------------------------
// Mock next/navigation
// ---------------------------------------------------------------------------
const mockReplace = jest.fn()
let mockSearchParams = new URLSearchParams()

jest.mock('next/navigation', () => ({
  useSearchParams: () => mockSearchParams,
  useRouter: () => ({ replace: mockReplace }),
}))

// ---------------------------------------------------------------------------
// Mock next/dynamic — resolve all dynamic imports synchronously
// ---------------------------------------------------------------------------
jest.mock('next/dynamic', () => {
  return (loader: () => Promise<unknown>) => {
    const src = loader.toString()
    if (src.includes('DashboardContent')) {
      const Comp = () => <div data-testid="dashboard-content">Electricity Dashboard</div>
      Comp.displayName = 'DashboardContent'
      return Comp
    }
    if (src.includes('HeatingOilDashboard')) {
      const Comp = () => <div data-testid="heating-oil-dashboard">Heating Oil Dashboard</div>
      Comp.displayName = 'HeatingOilDashboard'
      return Comp
    }
    if (src.includes('PropaneDashboard')) {
      const Comp = () => <div data-testid="propane-dashboard">Propane Dashboard</div>
      Comp.displayName = 'PropaneDashboard'
      return Comp
    }
    if (src.includes('WaterDashboard')) {
      const Comp = () => <div data-testid="water-dashboard">Water Dashboard</div>
      Comp.displayName = 'WaterDashboard'
      return Comp
    }
    if (src.includes('CommunitySolarContent')) {
      const Comp = () => <div data-testid="community-solar-dashboard">Community Solar Dashboard</div>
      Comp.displayName = 'CommunitySolarContent'
      return Comp
    }
    const Stub = () => <div data-testid="dynamic-stub" />
    Stub.displayName = 'DynamicStub'
    return Stub
  }
})

// ---------------------------------------------------------------------------
// Mock settings store
// ---------------------------------------------------------------------------
let mockUtilityTypes: string[] = ['electricity', 'natural_gas']
let mockRegion = 'us_ct'

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      utilityTypes: mockUtilityTypes,
      region: mockRegion,
    }),
}))

// ---------------------------------------------------------------------------
// Mock API hooks
// ---------------------------------------------------------------------------
jest.mock('@/lib/hooks/useCombinedSavings', () => ({
  useCombinedSavings: () => ({
    data: {
      total_monthly_savings: 42.5,
      breakdown: [
        { utility_type: 'electricity', monthly_savings: 30.0 },
        { utility_type: 'natural_gas', monthly_savings: 12.5 },
      ],
      savings_rank_pct: 0.15,
    },
    isLoading: false,
    error: null,
  }),
}))

jest.mock('@/lib/hooks/useNeighborhood', () => ({
  useNeighborhoodComparison: () => ({
    data: {
      region: 'us_ct',
      utility_type: 'electricity',
      user_count: 50,
      percentile: 0.65,
      user_rate: 0.185,
      cheapest_supplier: 'Town Square Energy',
      cheapest_rate: 0.12,
      avg_rate: 0.175,
      potential_savings: 0.065,
    },
    isLoading: false,
    error: null,
  }),
}))

// Mock skeleton
jest.mock('@/components/ui/skeleton', () => ({
  Skeleton: ({ variant, width, height, className }: { variant?: string; width?: number; height?: number; className?: string }) => (
    <div data-testid="skeleton" data-variant={variant} data-width={width} data-height={height} className={className} />
  ),
}))

// ---------------------------------------------------------------------------
// Imports under test (after mocks)
// ---------------------------------------------------------------------------
import DashboardTabs from '@/components/dashboard/DashboardTabs'
import { AllUtilitiesTab } from '@/components/dashboard/AllUtilitiesTab'
import { CombinedSavingsCard } from '@/components/dashboard/CombinedSavingsCard'
import { NeighborhoodCard } from '@/components/dashboard/NeighborhoodCard'
import { UtilityTabShell } from '@/components/dashboard/UtilityTabShell'

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------
function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  mockSearchParams = new URLSearchParams()
  mockReplace.mockClear()
  mockUtilityTypes = ['electricity', 'natural_gas']
  mockRegion = 'us_ct'
})

// ===========================================================================
// DashboardTabs
// ===========================================================================
describe('DashboardTabs', () => {
  it('renders tab bar with visible tabs', () => {
    renderWithProviders(<DashboardTabs />)
    expect(screen.getByTestId('dashboard-tabs')).toBeInTheDocument()
    expect(screen.getByTestId('tab-bar')).toBeInTheDocument()
    expect(screen.getByTestId('tab-all')).toBeInTheDocument()
    expect(screen.getByTestId('tab-electricity')).toBeInTheDocument()
    expect(screen.getByTestId('tab-natural_gas')).toBeInTheDocument()
  })

  it('hides "All" tab when user has single utility', () => {
    mockUtilityTypes = ['electricity']
    renderWithProviders(<DashboardTabs />)
    expect(screen.queryByTestId('tab-all')).not.toBeInTheDocument()
    expect(screen.getByTestId('tab-electricity')).toBeInTheDocument()
  })

  it('defaults to "all" tab for multi-utility users', () => {
    renderWithProviders(<DashboardTabs />)
    const allTab = screen.getByTestId('tab-all')
    expect(allTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('all-utilities-tab')).toBeInTheDocument()
  })

  it('defaults to single utility tab for single-utility users', () => {
    mockUtilityTypes = ['electricity']
    renderWithProviders(<DashboardTabs />)
    const elecTab = screen.getByTestId('tab-electricity')
    expect(elecTab).toHaveAttribute('aria-selected', 'true')
  })

  it('respects ?tab= URL param', () => {
    mockSearchParams = new URLSearchParams('tab=electricity')
    renderWithProviders(<DashboardTabs />)
    const elecTab = screen.getByTestId('tab-electricity')
    expect(elecTab).toHaveAttribute('aria-selected', 'true')
  })

  it('ignores invalid ?tab= URL param', () => {
    mockSearchParams = new URLSearchParams('tab=invalid_utility')
    renderWithProviders(<DashboardTabs />)
    // Falls back to default "all"
    const allTab = screen.getByTestId('tab-all')
    expect(allTab).toHaveAttribute('aria-selected', 'true')
  })

  it('switches tab on click and updates URL', async () => {
    const user = userEvent.setup()
    renderWithProviders(<DashboardTabs />)
    await user.click(screen.getByTestId('tab-electricity'))
    expect(mockReplace).toHaveBeenCalledWith(
      expect.stringContaining('tab=electricity'),
      { scroll: false }
    )
  })

  it('only shows tabs for user-configured utilities', () => {
    mockUtilityTypes = ['electricity', 'heating_oil']
    renderWithProviders(<DashboardTabs />)
    expect(screen.getByTestId('tab-electricity')).toBeInTheDocument()
    expect(screen.getByTestId('tab-heating_oil')).toBeInTheDocument()
    expect(screen.queryByTestId('tab-natural_gas')).not.toBeInTheDocument()
    expect(screen.queryByTestId('tab-propane')).not.toBeInTheDocument()
  })

  it('renders AllUtilitiesTab when "all" tab is active', () => {
    renderWithProviders(<DashboardTabs />)
    expect(screen.getByTestId('all-utilities-tab')).toBeInTheDocument()
  })

  it('renders UtilityTabShell when specific utility tab is active', () => {
    mockSearchParams = new URLSearchParams('tab=electricity')
    renderWithProviders(<DashboardTabs />)
    expect(screen.getByTestId('utility-shell-electricity')).toBeInTheDocument()
  })
})

// ===========================================================================
// AllUtilitiesTab
// ===========================================================================
describe('AllUtilitiesTab', () => {
  it('renders combined savings and neighborhood cards', () => {
    renderWithProviders(<AllUtilitiesTab />)
    expect(screen.getByTestId('combined-savings-card')).toBeInTheDocument()
    expect(screen.getByTestId('neighborhood-card')).toBeInTheDocument()
  })

  it('renders per-utility summary cards', () => {
    renderWithProviders(<AllUtilitiesTab />)
    expect(screen.getByTestId('utility-summary-electricity')).toBeInTheDocument()
    expect(screen.getByTestId('utility-summary-natural_gas')).toBeInTheDocument()
  })
})

// ===========================================================================
// CombinedSavingsCard
// ===========================================================================
describe('CombinedSavingsCard', () => {
  it('renders total monthly savings', () => {
    renderWithProviders(<CombinedSavingsCard />)
    const card = screen.getByTestId('combined-savings-card')
    expect(card).toHaveTextContent('$42.50')
  })

  it('renders stacked bar chart', () => {
    renderWithProviders(<CombinedSavingsCard />)
    expect(screen.getByTestId('savings-bar')).toBeInTheDocument()
  })

  it('renders breakdown labels', () => {
    renderWithProviders(<CombinedSavingsCard />)
    const card = screen.getByTestId('combined-savings-card')
    expect(card).toHaveTextContent('electricity: $30.00')
    expect(card).toHaveTextContent('natural gas: $12.50')
  })

  it('renders percentile badge', () => {
    renderWithProviders(<CombinedSavingsCard />)
    expect(screen.getByTestId('savings-percentile')).toHaveTextContent('Top 85% of savers')
  })

  it('shows loading skeleton when loading', () => {
    jest.spyOn(require('@/lib/hooks/useCombinedSavings'), 'useCombinedSavings').mockReturnValueOnce({
      data: null,
      isLoading: true,
      error: null,
    })
    renderWithProviders(<CombinedSavingsCard />)
    expect(screen.getByTestId('combined-savings-loading')).toBeInTheDocument()
  })

  it('shows error state on failure', () => {
    jest.spyOn(require('@/lib/hooks/useCombinedSavings'), 'useCombinedSavings').mockReturnValueOnce({
      data: null,
      isLoading: false,
      error: new Error('fail'),
    })
    renderWithProviders(<CombinedSavingsCard />)
    expect(screen.getByTestId('combined-savings-error')).toBeInTheDocument()
  })
})

// ===========================================================================
// NeighborhoodCard
// ===========================================================================
describe('NeighborhoodCard', () => {
  it('renders rate comparison context', () => {
    renderWithProviders(<NeighborhoodCard />)
    const ctx = screen.getByTestId('neighborhood-context')
    expect(ctx).toHaveTextContent('$0.1850/kWh')
    expect(ctx).toHaveTextContent('$0.1750/kWh')
  })

  it('renders comparison bar chart', () => {
    renderWithProviders(<NeighborhoodCard />)
    expect(screen.getByTestId('neighborhood-bars')).toBeInTheDocument()
  })

  it('renders percentile text', () => {
    renderWithProviders(<NeighborhoodCard />)
    expect(screen.getByTestId('neighborhood-percentile')).toHaveTextContent(
      'You pay less than 65% of users in your area'
    )
  })

  it('renders cheapest supplier suggestion', () => {
    renderWithProviders(<NeighborhoodCard />)
    expect(screen.getByTestId('neighborhood-savings')).toHaveTextContent('Town Square Energy')
    expect(screen.getByTestId('neighborhood-savings')).toHaveTextContent('$0.0650/kWh')
  })

  it('shows insufficient data placeholder when percentile is null', () => {
    jest.spyOn(require('@/lib/hooks/useNeighborhood'), 'useNeighborhoodComparison').mockReturnValueOnce({
      data: { percentile: null, user_rate: null, avg_rate: null },
      isLoading: false,
      error: null,
    })
    renderWithProviders(<NeighborhoodCard />)
    expect(screen.getByTestId('neighborhood-insufficient')).toBeInTheDocument()
    expect(screen.getByTestId('neighborhood-insufficient')).toHaveTextContent(
      'We need a few more neighbors'
    )
  })

  it('shows loading skeleton when loading', () => {
    jest.spyOn(require('@/lib/hooks/useNeighborhood'), 'useNeighborhoodComparison').mockReturnValueOnce({
      data: null,
      isLoading: true,
      error: null,
    })
    renderWithProviders(<NeighborhoodCard />)
    expect(screen.getByTestId('neighborhood-loading')).toBeInTheDocument()
  })

  it('shows error state on failure', () => {
    jest.spyOn(require('@/lib/hooks/useNeighborhood'), 'useNeighborhoodComparison').mockReturnValueOnce({
      data: null,
      isLoading: false,
      error: new Error('fail'),
    })
    renderWithProviders(<NeighborhoodCard />)
    expect(screen.getByTestId('neighborhood-error')).toBeInTheDocument()
  })
})

// ===========================================================================
// UtilityTabShell
// ===========================================================================
describe('UtilityTabShell', () => {
  it('renders electricity dashboard for electricity type', () => {
    renderWithProviders(<UtilityTabShell utilityType="electricity" />)
    expect(screen.getByTestId('utility-shell-electricity')).toBeInTheDocument()
    expect(screen.getByTestId('dashboard-content')).toBeInTheDocument()
  })

  it('renders heating oil dashboard', () => {
    renderWithProviders(<UtilityTabShell utilityType="heating_oil" />)
    expect(screen.getByTestId('utility-shell-heating_oil')).toBeInTheDocument()
    expect(screen.getByTestId('heating-oil-dashboard')).toBeInTheDocument()
  })

  it('renders placeholder for natural gas (no dashboard yet)', () => {
    renderWithProviders(<UtilityTabShell utilityType="natural_gas" />)
    expect(screen.getByTestId('utility-shell-placeholder-natural_gas')).toBeInTheDocument()
    expect(screen.getByText('Dashboard coming soon. Check back for detailed analytics.')).toBeInTheDocument()
  })
})
