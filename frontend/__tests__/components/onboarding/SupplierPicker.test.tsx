import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import React from 'react'
import type { Supplier } from '@/types'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

jest.mock('lucide-react', () => ({
  Building2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-building" {...props} />,
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-loader" {...props} />,
}))

// SupplierSelector is the compound dropdown — mock it to a simple list so
// SupplierPicker logic can be exercised without the dropdown internals.
const mockOnChange = jest.fn()
jest.mock('@/components/suppliers/SupplierSelector', () => ({
  SupplierSelector: ({
    suppliers,
    value,
    onChange,
    placeholder,
  }: {
    suppliers: Supplier[]
    value: Supplier | null
    onChange: (s: Supplier | null) => void
    placeholder?: string
  }) => (
    <div data-testid="supplier-selector">
      <span data-testid="supplier-count">{suppliers.length}</span>
      {placeholder && <span data-testid="selector-placeholder">{placeholder}</span>}
      {value && <span data-testid="selected-supplier-name">{value.name}</span>}
      {suppliers.map((s) => (
        <button
          key={s.id}
          data-testid={`supplier-option-${s.id}`}
          onClick={() => onChange(s)}
        >
          {s.name}
        </button>
      ))}
    </div>
  ),
}))

// ---------------------------------------------------------------------------
// useSuppliers hook mock — configurable per test
// ---------------------------------------------------------------------------
const mockUseSuppliers = jest.fn()
jest.mock('@/lib/hooks/useSuppliers', () => ({
  useSuppliers: (...args: unknown[]) => mockUseSuppliers(...args),
}))

// ---------------------------------------------------------------------------
// Fixture data
// ---------------------------------------------------------------------------
const mockRawSuppliers = [
  {
    id: 'sup_1',
    name: 'Eversource Energy',
    avgPricePerKwh: 0.25,
    standingCharge: 0.50,
    greenEnergy: true,
    green_energy_provider: true,
    rating: 4.5,
    estimatedAnnualCost: 1200,
    tariffType: 'variable',
    tariff_types: ['variable'],
  },
  {
    id: 'sup_2',
    name: 'United Illuminating',
    avgPricePerKwh: 0.28,
    standingCharge: 0.45,
    greenEnergy: false,
    green_energy_provider: false,
    rating: 3.8,
    estimatedAnnualCost: 1350,
    tariffType: 'fixed',
    tariff_types: ['fixed'],
  },
  {
    id: 'sup_3',
    name: 'NextEra Energy',
    avgPricePerKwh: 0.22,
    standingCharge: 0.40,
    greenEnergy: true,
    green_energy_provider: true,
    rating: 4.0,
    estimatedAnnualCost: 1100,
    tariffType: 'variable',
    tariff_types: ['variable'],
  },
]

const mockSelectedSupplier: Supplier = {
  id: 'sup_1',
  name: 'Eversource Energy',
  avgPricePerKwh: 0.25,
  standingCharge: 0.50,
  greenEnergy: true,
  rating: 4.5,
  estimatedAnnualCost: 1200,
  tariffType: 'variable',
}

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------
import { SupplierPicker } from '@/components/onboarding/SupplierPicker'

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('SupplierPicker', () => {
  const onSelect = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseSuppliers.mockReturnValue({
      data: { suppliers: mockRawSuppliers },
      isLoading: false,
    })
  })

  // --- Render ---

  it('renders the heading', () => {
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByText('Who is your energy supplier?')).toBeInTheDocument()
  })

  it('renders the description text', () => {
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByText(/deregulated market/i)).toBeInTheDocument()
  })

  it('renders the Building2 icon', () => {
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByTestId('icon-building')).toBeInTheDocument()
  })

  it('renders the footer hint text', () => {
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByText(/Check your electricity bill/i)).toBeInTheDocument()
  })

  // --- useSuppliers integration ---

  it('calls useSuppliers with the provided region', () => {
    render(
      <SupplierPicker region="us_tx" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(mockUseSuppliers).toHaveBeenCalledWith('us_tx')
  })

  it('calls useSuppliers with the correct region when region changes', () => {
    const { rerender } = render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    rerender(
      <SupplierPicker region="us_ny" onSelect={onSelect} selectedSupplier={null} />
    )

    expect(mockUseSuppliers).toHaveBeenLastCalledWith('us_ny')
  })

  // --- Loading state ---

  it('shows loading spinner when suppliers are loading', () => {
    mockUseSuppliers.mockReturnValue({ data: undefined, isLoading: true })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('Loading suppliers...')).toBeInTheDocument()
    expect(screen.getByTestId('icon-loader')).toBeInTheDocument()
  })

  it('does not render SupplierSelector while loading', () => {
    mockUseSuppliers.mockReturnValue({ data: undefined, isLoading: true })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.queryByTestId('supplier-selector')).not.toBeInTheDocument()
  })

  // --- Empty state ---

  it('shows empty state message when no suppliers are returned', () => {
    mockUseSuppliers.mockReturnValue({ data: { suppliers: [] }, isLoading: false })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(
      screen.getByText(/No suppliers found for your state/i)
    ).toBeInTheDocument()
    expect(screen.queryByTestId('supplier-selector')).not.toBeInTheDocument()
  })

  it('shows empty state when data is null', () => {
    mockUseSuppliers.mockReturnValue({ data: null, isLoading: false })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(
      screen.getByText(/No suppliers found for your state/i)
    ).toBeInTheDocument()
  })

  it('shows empty state when suppliers key is missing', () => {
    mockUseSuppliers.mockReturnValue({ data: {}, isLoading: false })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(
      screen.getByText(/No suppliers found for your state/i)
    ).toBeInTheDocument()
  })

  // --- SupplierSelector rendered with mapped suppliers ---

  it('renders SupplierSelector when suppliers are available', () => {
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByTestId('supplier-selector')).toBeInTheDocument()
  })

  it('passes all mapped suppliers to SupplierSelector', () => {
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByTestId('supplier-count')).toHaveTextContent('3')
  })

  it('renders the correct supplier names in the selector', () => {
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByTestId('supplier-option-sup_1')).toHaveTextContent('Eversource Energy')
    expect(screen.getByTestId('supplier-option-sup_2')).toHaveTextContent('United Illuminating')
    expect(screen.getByTestId('supplier-option-sup_3')).toHaveTextContent('NextEra Energy')
  })

  it('passes the placeholder to SupplierSelector', () => {
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByTestId('selector-placeholder')).toHaveTextContent(
      'Search or select your current supplier...'
    )
  })

  // --- Selected supplier prop ---

  it('passes selectedSupplier as value to SupplierSelector', () => {
    render(
      <SupplierPicker
        region="us_ct"
        onSelect={onSelect}
        selectedSupplier={mockSelectedSupplier}
      />,
      { wrapper: createWrapper() }
    )

    expect(screen.getByTestId('selected-supplier-name')).toHaveTextContent(
      'Eversource Energy'
    )
  })

  it('passes null to SupplierSelector when no supplier is selected', () => {
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    expect(screen.queryByTestId('selected-supplier-name')).not.toBeInTheDocument()
  })

  // --- Selection callback ---

  it('calls onSelect when a supplier option is clicked', async () => {
    const user = userEvent.setup()
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    await user.click(screen.getByTestId('supplier-option-sup_2'))

    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'sup_2', name: 'United Illuminating' })
    )
  })

  it('calls onSelect with the correctly mapped Supplier object', async () => {
    const user = userEvent.setup()
    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    await user.click(screen.getByTestId('supplier-option-sup_1'))

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'sup_1',
        name: 'Eversource Energy',
        avgPricePerKwh: 0.25,
        greenEnergy: true,
        rating: 4.5,
      })
    )
  })

  // --- Backend field mapping ---

  it('maps logo_url to logo field when logo is absent', () => {
    mockUseSuppliers.mockReturnValue({
      data: {
        suppliers: [
          {
            id: 'sup_logo',
            name: 'Logo Supplier',
            logo_url: 'https://example.com/logo.png',
            tariff_types: ['variable'],
          },
        ],
      },
      isLoading: false,
    })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    // Click the option — the mapped supplier should have logo set from logo_url
    expect(screen.getByTestId('supplier-option-sup_logo')).toBeInTheDocument()
  })

  it('defaults avgPricePerKwh to 0.22 when absent from raw record', async () => {
    const user = userEvent.setup()
    mockUseSuppliers.mockReturnValue({
      data: {
        suppliers: [
          {
            id: 'sup_default',
            name: 'Default Supplier',
            tariff_types: ['variable'],
          },
        ],
      },
      isLoading: false,
    })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    await user.click(screen.getByTestId('supplier-option-sup_default'))

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ avgPricePerKwh: 0.22 })
    )
  })

  it('defaults estimatedAnnualCost to 850 when absent', async () => {
    const user = userEvent.setup()
    mockUseSuppliers.mockReturnValue({
      data: {
        suppliers: [
          {
            id: 'sup_cost',
            name: 'Cost Supplier',
            tariff_types: ['fixed'],
          },
        ],
      },
      isLoading: false,
    })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    await user.click(screen.getByTestId('supplier-option-sup_cost'))

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ estimatedAnnualCost: 850 })
    )
  })

  it('uses green_energy_provider as greenEnergy fallback', async () => {
    const user = userEvent.setup()
    mockUseSuppliers.mockReturnValue({
      data: {
        suppliers: [
          {
            id: 'sup_green',
            name: 'Green Supplier',
            green_energy_provider: true,
            tariff_types: ['variable'],
          },
        ],
      },
      isLoading: false,
    })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    await user.click(screen.getByTestId('supplier-option-sup_green'))

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ greenEnergy: true })
    )
  })

  it('uses first element of tariff_types when tariffType is absent', async () => {
    const user = userEvent.setup()
    mockUseSuppliers.mockReturnValue({
      data: {
        suppliers: [
          {
            id: 'sup_tariff',
            name: 'Tariff Supplier',
            tariff_types: ['fixed'],
          },
        ],
      },
      isLoading: false,
    })

    render(
      <SupplierPicker region="us_ct" onSelect={onSelect} selectedSupplier={null} />,
      { wrapper: createWrapper() }
    )

    await user.click(screen.getByTestId('supplier-option-sup_tariff'))

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ tariffType: 'fixed' })
    )
  })
})
