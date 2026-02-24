import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SuppliersPage from '@/app/(app)/suppliers/page'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import React from 'react'

// Mock settings store with configurable region
let mockRegion = 'us_ct'
const mockCurrentSupplier = {
  id: '1',
  name: 'Eversource Energy',
  avgPricePerKwh: 0.25,
  standingCharge: 0.50,
  greenEnergy: true,
  rating: 4.5,
  estimatedAnnualCost: 1200,
  tariffType: 'variable' as const,
}

jest.mock('@/lib/store/settings', () => ({
  useSettingsStore: (selector: (state: any) => any) =>
    selector({
      region: mockRegion,
      annualUsageKwh: 10500,
      currentSupplier: mockCurrentSupplier,
      setCurrentSupplier: jest.fn(),
    }),
}))

// Mock API modules
const mockGetSuppliers = jest.fn()
const mockGetRecommendation = jest.fn()
const mockCompareSuppliers = jest.fn()
const mockInitiateSwitch = jest.fn()

jest.mock('@/lib/api/suppliers', () => ({
  getSuppliers: (...args: any[]) => mockGetSuppliers(...args),
  getSupplier: jest.fn(),
  getRecommendation: (...args: any[]) => mockGetRecommendation(...args),
  compareSuppliers: (...args: any[]) => mockCompareSuppliers(...args),
  initiateSwitch: (...args: any[]) => mockInitiateSwitch(...args),
  getSwitchStatus: jest.fn(),
}))

// Mock Next.js Image
jest.mock('next/image', () => ({
  __esModule: true,
  default: (props: any) => {
    // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
    return <img {...props} />
  },
}))

// Supplier test data
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

describe('SuppliersPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    mockRegion = 'us_ct'

    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    })

    mockGetSuppliers.mockResolvedValue({ suppliers: mockSuppliers })
    mockGetRecommendation.mockResolvedValue({
      recommendation: {
        supplier: mockSuppliers[1],
        currentSupplier: mockCurrentSupplier,
        estimatedSavings: 150,
        paybackMonths: 0,
        confidence: 0.85,
      },
    })
  })

  afterEach(() => {
    queryClient.clear()
    jest.clearAllMocks()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  it('renders supplier list', async () => {
    render(<SuppliersPage />, { wrapper })

    await waitFor(() => {
      // Eversource appears in supplier card + "Your Current" card, so use getAllByText
      expect(screen.getAllByText('Eversource Energy').length).toBeGreaterThanOrEqual(1)
      // NextEra may appear in recommendation banner + card
      expect(screen.getAllByText('NextEra Energy').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('United Illuminating').length).toBeGreaterThanOrEqual(1)
      // Verify correct supplier count heading
      expect(screen.getByText('3 Suppliers Available')).toBeInTheDocument()
    })
  })

  it('renders supplier comparison cards', async () => {
    render(<SuppliersPage />, { wrapper })

    await waitFor(() => {
      // Stats row cards
      expect(screen.getByText('Cheapest Option')).toBeInTheDocument()
      expect(screen.getByText('Greenest Option')).toBeInTheDocument()
      expect(screen.getByText('Your Current')).toBeInTheDocument()
    })
  })

  it('shows loading state while fetching', () => {
    mockGetSuppliers.mockReturnValue(new Promise(() => {}))
    mockGetRecommendation.mockReturnValue(new Promise(() => {}))

    render(<SuppliersPage />, { wrapper })

    // Should show skeleton loading placeholders
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('handles empty supplier list', async () => {
    mockGetSuppliers.mockResolvedValue({ suppliers: [] })

    render(<SuppliersPage />, { wrapper })

    await waitFor(() => {
      expect(screen.getByText('0 Suppliers Available')).toBeInTheDocument()
    })
  })

  it('displays supplier ratings', async () => {
    render(<SuppliersPage />, { wrapper })

    await waitFor(() => {
      // Ratings may appear multiple times (card + "Your Current" stat)
      expect(screen.getAllByText('4.5').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('4.3').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('3.8').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('displays green energy badges', async () => {
    render(<SuppliersPage />, { wrapper })

    await waitFor(() => {
      // Two green energy suppliers (Eversource and NextEra)
      const greenBadges = screen.getAllByText(/Green Energy/)
      expect(greenBadges.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('handles API errors', async () => {
    mockGetSuppliers.mockRejectedValue(new Error('Network error'))
    mockGetRecommendation.mockRejectedValue(new Error('Network error'))

    render(<SuppliersPage />, { wrapper })

    await waitFor(() => {
      // Page should still render without crashing
      expect(screen.getByText('Compare Suppliers')).toBeInTheDocument()
      // Should show 0 suppliers since API failed
      expect(screen.getByText('0 Suppliers Available')).toBeInTheDocument()
    })
  })

  it('filters suppliers by region', async () => {
    render(<SuppliersPage />, { wrapper })

    await waitFor(() => {
      // Wait for suppliers to load
      expect(screen.getByText('3 Suppliers Available')).toBeInTheDocument()
    })

    // Verify the API was called with the correct region
    expect(mockGetSuppliers).toHaveBeenCalledWith('us_ct', 10500)
  })

  it('shows estimated annual cost', async () => {
    render(<SuppliersPage />, { wrapper })

    await waitFor(() => {
      // Check for formatted annual costs in supplier cards
      expect(screen.getAllByText(/1,200/).length).toBeGreaterThan(0)
      expect(screen.getAllByText(/1,050/).length).toBeGreaterThan(0)
    })
  })

  it('renders switch buttons for non-current suppliers', async () => {
    render(<SuppliersPage />, { wrapper })

    await waitFor(() => {
      // Should have switch buttons for non-current suppliers
      const switchButtons = screen.getAllByRole('button', { name: /switch/i })
      expect(switchButtons.length).toBeGreaterThan(0)
    })
  })
})
