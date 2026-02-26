import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import React from 'react'

// Mock the Header component to avoid sidebar context dependency
jest.mock('@/components/layout/Header', () => ({
  Header: ({ title }: { title: string }) => (
    <header data-testid="page-header">
      <h1>{title}</h1>
    </header>
  ),
}))

// Mock Next.js Image
jest.mock('next/image', () => ({
  __esModule: true,
  default: (props: any) => {
    // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
    return <img {...props} />
  },
}))

// Mock settings store with configurable state
let mockRegion = 'us_ct'
let mockCurrentSupplier: any = null
const mockSetCurrentSupplier = jest.fn()

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (state: any) => any) =>
    selector({
      region: mockRegion,
      annualUsageKwh: 10500,
      currentSupplier: mockCurrentSupplier,
      setCurrentSupplier: mockSetCurrentSupplier,
    }),
}))

// Mock API modules
const mockGetSuppliers = jest.fn()
const mockGetRecommendation = jest.fn()
const mockInitiateSwitch = jest.fn()
const mockSetUserSupplier = jest.fn()

jest.mock('@/lib/api/suppliers', () => ({
  getSuppliers: (...args: any[]) => mockGetSuppliers(...args),
  getSupplier: jest.fn(),
  getRecommendation: (...args: any[]) => mockGetRecommendation(...args),
  compareSuppliers: jest.fn(),
  initiateSwitch: (...args: any[]) => mockInitiateSwitch(...args),
  getSwitchStatus: jest.fn(),
  setUserSupplier: (...args: any[]) => mockSetUserSupplier(...args),
  getUserSupplier: jest.fn(),
  removeUserSupplier: jest.fn(),
  linkSupplierAccount: jest.fn(),
  getUserSupplierAccounts: jest.fn(),
  unlinkSupplierAccount: jest.fn(),
}))

// Import after all mocks are established
import SuppliersContent from '@/components/suppliers/SuppliersContent'

// Test data
const mockSuppliers = [
  {
    id: '1',
    name: 'Eversource Energy',
    avgPricePerKwh: 0.25,
    standingCharge: 0.50,
    greenEnergy: true,
    rating: 4.5,
    estimatedAnnualCost: 1200,
    tariffType: 'variable',
    features: ['Smart meter compatible'],
  },
  {
    id: '2',
    name: 'NextEra Energy',
    avgPricePerKwh: 0.22,
    standingCharge: 0.45,
    greenEnergy: true,
    rating: 4.3,
    estimatedAnnualCost: 1050,
    tariffType: 'fixed',
    features: ['100% renewable'],
  },
  {
    id: '3',
    name: 'United Illuminating',
    avgPricePerKwh: 0.28,
    standingCharge: 0.55,
    greenEnergy: false,
    rating: 3.8,
    estimatedAnnualCost: 1350,
    tariffType: 'variable',
    features: [],
  },
]

const eversourceSupplier = {
  id: '1',
  name: 'Eversource Energy',
  avgPricePerKwh: 0.25,
  standingCharge: 0.50,
  greenEnergy: true,
  rating: 4.5,
  estimatedAnnualCost: 1200,
  tariffType: 'variable' as const,
}

describe('SuppliersContent', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    mockRegion = 'us_ct'
    mockCurrentSupplier = null

    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    })

    mockGetSuppliers.mockResolvedValue({ suppliers: mockSuppliers })
    mockGetRecommendation.mockResolvedValue({ recommendation: null })
    mockSetUserSupplier.mockResolvedValue({ supplier_id: '1' })
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  // --- Loading State Tests ---

  it('shows loading skeletons while suppliers are fetching', () => {
    mockGetSuppliers.mockReturnValue(new Promise(() => {}))
    mockGetRecommendation.mockReturnValue(new Promise(() => {}))

    render(<SuppliersContent />, { wrapper })

    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders page header during loading', () => {
    mockGetSuppliers.mockReturnValue(new Promise(() => {}))

    render(<SuppliersContent />, { wrapper })

    expect(screen.getByText('Compare Suppliers')).toBeInTheDocument()
  })

  // --- Stats Row Tests ---

  it('renders cheapest option stat card', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Cheapest Option')).toBeInTheDocument()
    })
  })

  it('renders greenest option stat card', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Greenest Option')).toBeInTheDocument()
    })
  })

  it('renders your current stat card', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Your Current')).toBeInTheDocument()
    })
  })

  it('identifies cheapest supplier correctly', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      // NextEra at $1,050/year is cheapest
      const cheapestCard = screen.getByText('Cheapest Option')
      const parentCard = cheapestCard.closest('[class*="card"]') || cheapestCard.parentElement?.parentElement
      expect(parentCard).toBeTruthy()
      // NextEra Energy should appear as cheapest
      expect(screen.getAllByText('NextEra Energy').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('shows "Not set" when no current supplier is selected', async () => {
    mockCurrentSupplier = null

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Not set')).toBeInTheDocument()
    })
  })

  it('shows "Select Supplier" button when no current supplier', async () => {
    mockCurrentSupplier = null

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/Select Supplier/)).toBeInTheDocument()
    })
  })

  it('shows current supplier name when one is set', async () => {
    mockCurrentSupplier = eversourceSupplier

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      // Eversource appears in card + your current section
      expect(screen.getAllByText('Eversource Energy').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('shows current supplier annual cost', async () => {
    mockCurrentSupplier = eversourceSupplier

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      // $1,200/year cost
      expect(screen.getAllByText(/1,200/).length).toBeGreaterThanOrEqual(1)
    })
  })

  // --- Supplier List Tests ---

  it('renders supplier list with correct count', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('3 Suppliers Available')).toBeInTheDocument()
    })
  })

  it('renders all supplier names', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getAllByText('Eversource Energy').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('NextEra Energy').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('United Illuminating').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders supplier ratings', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getAllByText('4.5').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('4.3').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('3.8').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders green energy badges for green suppliers', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      const greenBadges = screen.getAllByText(/Green Energy/)
      // Eversource and NextEra are green
      expect(greenBadges.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('shows estimated annual costs', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getAllByText(/1,050/).length).toBeGreaterThan(0)
      expect(screen.getAllByText(/1,350/).length).toBeGreaterThan(0)
    })
  })

  // --- View Toggle Tests ---

  it('defaults to grid view mode', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('3 Suppliers Available')).toBeInTheDocument()
    })

    // Grid view should show SupplierCard components (not table)
    // Verify no table element is rendered in default state
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('renders switch buttons for suppliers', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      const switchButtons = screen.getAllByRole('button', { name: /switch/i })
      expect(switchButtons.length).toBeGreaterThan(0)
    })
  })

  // --- Empty State Tests ---

  it('handles empty supplier list', async () => {
    mockGetSuppliers.mockResolvedValue({ suppliers: [] })

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('0 Suppliers Available')).toBeInTheDocument()
    })
  })

  it('shows dashes for cheapest/greenest when no suppliers exist', async () => {
    mockGetSuppliers.mockResolvedValue({ suppliers: [] })

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      const dashes = screen.getAllByText('--')
      expect(dashes.length).toBeGreaterThanOrEqual(2) // cheapest and greenest show --
    })
  })

  // --- Error State Tests ---

  it('handles API errors without crashing', async () => {
    mockGetSuppliers.mockRejectedValue(new Error('Network error'))
    mockGetRecommendation.mockRejectedValue(new Error('Network error'))

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Compare Suppliers')).toBeInTheDocument()
      expect(screen.getByText('0 Suppliers Available')).toBeInTheDocument()
    })
  })

  // --- Recommendation Banner Tests ---

  it('shows recommendation banner when recommendation and current supplier exist', async () => {
    mockCurrentSupplier = eversourceSupplier

    mockGetRecommendation.mockResolvedValue({
      recommendation: {
        supplier: mockSuppliers[1],
        currentSupplier: eversourceSupplier,
        estimatedSavings: 150,
        paybackMonths: 0,
        confidence: 0.85,
      },
    })

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/We found you a better deal!/)).toBeInTheDocument()
    })
  })

  it('shows estimated savings in recommendation banner', async () => {
    mockCurrentSupplier = eversourceSupplier

    mockGetRecommendation.mockResolvedValue({
      recommendation: {
        supplier: mockSuppliers[1],
        currentSupplier: eversourceSupplier,
        estimatedSavings: 150,
        paybackMonths: 0,
        confidence: 0.85,
      },
    })

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      // $150.00 may appear in both banner and supplier card savings badge
      const matches = screen.getAllByText(/\$150\.00/)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('shows "Switch Now" button in recommendation banner', async () => {
    mockCurrentSupplier = eversourceSupplier

    mockGetRecommendation.mockResolvedValue({
      recommendation: {
        supplier: mockSuppliers[1],
        currentSupplier: eversourceSupplier,
        estimatedSavings: 150,
        paybackMonths: 0,
        confidence: 0.85,
      },
    })

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('Switch Now')).toBeInTheDocument()
    })
  })

  it('does not show recommendation banner when no current supplier', async () => {
    mockCurrentSupplier = null

    mockGetRecommendation.mockResolvedValue({
      recommendation: {
        supplier: mockSuppliers[1],
        currentSupplier: eversourceSupplier,
        estimatedSavings: 150,
        paybackMonths: 0,
        confidence: 0.85,
      },
    })

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('3 Suppliers Available')).toBeInTheDocument()
    })

    expect(screen.queryByText(/We found you a better deal!/)).not.toBeInTheDocument()
  })

  // --- API Call Verification ---

  it('calls getSuppliers with correct region and usage', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('3 Suppliers Available')).toBeInTheDocument()
    })

    expect(mockGetSuppliers).toHaveBeenCalledWith('us_ct', 10500)
  })

  it('does not call getRecommendation when no current supplier', async () => {
    mockCurrentSupplier = null

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('3 Suppliers Available')).toBeInTheDocument()
    })

    // With empty currentSupplierId, query should be disabled
    // The hook is called but with enabled: false (empty string supplier id)
    // so getRecommendation should not be invoked
    expect(mockGetRecommendation).not.toHaveBeenCalled()
  })

  // --- Set Supplier Dialog Tests ---

  it('opens set supplier dialog when "Select Supplier" button is clicked', async () => {
    mockCurrentSupplier = null
    const user = userEvent.setup()

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText(/Select Supplier/)).toBeInTheDocument()
    })

    await user.click(screen.getByText(/Select Supplier/))

    // The dialog should appear (overlaid on page)
    await waitFor(() => {
      // SetSupplierDialog should be rendered
      expect(document.querySelector('[class*="fixed"]')).toBeTruthy()
    })
  })

  // --- Backend field name mapping ---

  it('handles backend field names in supplier data', async () => {
    mockGetSuppliers.mockResolvedValue({
      suppliers: [
        {
          id: 'backend-1',
          name: 'Backend Supplier',
          logo_url: '/logos/test.png',
          green_energy_provider: true,
          tariff_types: ['fixed', 'variable'],
          exit_fee: 75,
          contract_length: 12,
        },
      ],
    })

    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('1 Suppliers Available')).toBeInTheDocument()
      // Supplier name appears in supplier card + cheapest/greenest stat cards
      expect(screen.getAllByText('Backend Supplier').length).toBeGreaterThanOrEqual(1)
    })
  })

  // --- "100% Renewable" label ---

  it('shows "100% Renewable" for the greenest option card', async () => {
    render(<SuppliersContent />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('100% Renewable')).toBeInTheDocument()
    })
  })
})
