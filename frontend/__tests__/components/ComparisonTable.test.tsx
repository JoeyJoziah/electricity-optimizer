import { render, screen, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ComparisonTable } from '@/components/suppliers/ComparisonTable'
import '@testing-library/jest-dom'

const mockSuppliers = [
  {
    id: '1',
    name: 'Eversource Energy',
    avgPricePerKwh: 0.25,
    standingCharge: 0.50,
    greenEnergy: true,
    rating: 4.5,
    estimatedAnnualCost: 1200,
    tariffType: 'variable' as const,
  },
  {
    id: '2',
    name: 'NextEra Energy',
    avgPricePerKwh: 0.22,
    standingCharge: 0.45,
    greenEnergy: true,
    rating: 4.3,
    estimatedAnnualCost: 1050,
    tariffType: 'variable' as const,
  },
  {
    id: '3',
    name: 'United Illuminating (UI)',
    avgPricePerKwh: 0.28,
    standingCharge: 0.55,
    greenEnergy: false,
    rating: 3.8,
    estimatedAnnualCost: 1350,
    tariffType: 'fixed' as const,
  },
]

describe('ComparisonTable', () => {
  it('renders all suppliers in the table', () => {
    render(<ComparisonTable suppliers={mockSuppliers} />)

    expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
    expect(screen.getByText('NextEra Energy')).toBeInTheDocument()
    expect(screen.getByText('United Illuminating (UI)')).toBeInTheDocument()
  })

  it('displays column headers correctly', () => {
    render(<ComparisonTable suppliers={mockSuppliers} />)

    expect(screen.getByText(/supplier/i)).toBeInTheDocument()
    expect(screen.getByText(/price.*kwh/i)).toBeInTheDocument()
    expect(screen.getByText(/standing charge/i)).toBeInTheDocument()
    expect(screen.getByText(/annual cost/i)).toBeInTheDocument()
    expect(screen.getByText(/rating/i)).toBeInTheDocument()
  })

  it('sorts by price by default (ascending)', () => {
    render(<ComparisonTable suppliers={mockSuppliers} />)

    const rows = screen.getAllByRole('row')
    // First data row should be NextEra (cheapest)
    expect(within(rows[1]).getByText('NextEra Energy')).toBeInTheDocument()
  })

  it('allows sorting by different columns', async () => {
    const user = userEvent.setup()
    render(<ComparisonTable suppliers={mockSuppliers} />)

    // Sort by rating (first click = ascending, lowest first)
    await act(async () => {
      await user.click(screen.getByText(/rating/i))
    })

    const rows = screen.getAllByRole('row')
    // First data row should be United Illuminating (lowest rating 3.8)
    expect(within(rows[1]).getByText('United Illuminating (UI)')).toBeInTheDocument()
  })

  it('toggles sort direction on repeated clicks', async () => {
    const user = userEvent.setup()
    render(<ComparisonTable suppliers={mockSuppliers} />)

    // Default sort is already estimatedAnnualCost ASC
    // First click on annual cost toggles to descending
    await act(async () => {
      await user.click(screen.getByText(/annual cost/i))
    })
    let rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('United Illuminating (UI)')).toBeInTheDocument()

    // Second click toggles back to ascending
    await act(async () => {
      await user.click(screen.getByText(/annual cost/i))
    })
    rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('NextEra Energy')).toBeInTheDocument()
  })

  it('highlights the cheapest option', () => {
    render(<ComparisonTable suppliers={mockSuppliers} />)

    const cheapestRow = screen.getByTestId('supplier-row-2')
    expect(cheapestRow).toHaveClass('bg-success-50')
  })

  it('shows green energy indicator for renewable suppliers', () => {
    render(<ComparisonTable suppliers={mockSuppliers} />)

    const octopusRow = screen.getByTestId('supplier-row-1')
    expect(within(octopusRow).getByTestId('green-badge')).toBeInTheDocument()

    const bgRow = screen.getByTestId('supplier-row-3')
    expect(within(bgRow).queryByTestId('green-badge')).not.toBeInTheDocument()
  })

  it('calls onSelect when a row is clicked', async () => {
    const onSelect = jest.fn()
    const user = userEvent.setup()

    render(<ComparisonTable suppliers={mockSuppliers} onSelect={onSelect} />)

    await user.click(screen.getByTestId('supplier-row-1'))

    expect(onSelect).toHaveBeenCalledWith(mockSuppliers[0])
  })

  it('shows savings compared to current supplier', () => {
    const currentSupplier = mockSuppliers[2] // United Illuminating - 1350/year

    render(
      <ComparisonTable
        suppliers={mockSuppliers}
        currentSupplierId={currentSupplier.id}
      />
    )

    // Bulb should show savings of 300
    const bulbRow = screen.getByTestId('supplier-row-2')
    expect(within(bulbRow).getByText(/300/)).toBeInTheDocument()
  })

  it('renders empty state when no suppliers provided', () => {
    render(<ComparisonTable suppliers={[]} />)

    expect(screen.getByText(/no suppliers available/i)).toBeInTheDocument()
  })

  it('is accessible with proper table semantics', () => {
    render(<ComparisonTable suppliers={mockSuppliers} />)

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getAllByRole('columnheader')).toHaveLength(6) // Including actions
    expect(screen.getAllByRole('row')).toHaveLength(4) // Header + 3 data rows
  })

  it('supports filtering by green energy only', async () => {
    const user = userEvent.setup()
    render(<ComparisonTable suppliers={mockSuppliers} showFilters />)

    await user.click(screen.getByRole('checkbox', { name: /green energy only/i }))

    expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
    expect(screen.getByText('NextEra Energy')).toBeInTheDocument()
    expect(screen.queryByText('United Illuminating (UI)')).not.toBeInTheDocument()
  })
})
