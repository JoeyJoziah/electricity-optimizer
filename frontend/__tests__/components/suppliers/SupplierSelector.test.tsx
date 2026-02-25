import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SupplierSelector } from '@/components/suppliers/SupplierSelector'
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
    tariffType: 'variable',
  },
  {
    id: '2',
    name: 'United Illuminating',
    avgPricePerKwh: 0.28,
    standingCharge: 0.45,
    greenEnergy: false,
    rating: 3.8,
    estimatedAnnualCost: 1350,
    tariffType: 'fixed',
  },
  {
    id: '3',
    name: 'NextEra Energy',
    avgPricePerKwh: 0.22,
    standingCharge: 0.40,
    greenEnergy: true,
    rating: 4.0,
    estimatedAnnualCost: 1100,
    tariffType: 'variable',
  },
]

describe('SupplierSelector', () => {
  it('renders placeholder when no value', () => {
    render(
      <SupplierSelector
        suppliers={mockSuppliers}
        value={null}
        onChange={jest.fn()}
        placeholder="Pick a supplier..."
      />
    )

    expect(screen.getByText('Pick a supplier...')).toBeInTheDocument()
  })

  it('renders default placeholder when no custom placeholder', () => {
    render(
      <SupplierSelector
        suppliers={mockSuppliers}
        value={null}
        onChange={jest.fn()}
      />
    )

    expect(screen.getByText('Select a supplier...')).toBeInTheDocument()
  })

  it('renders selected supplier name when value set', () => {
    render(
      <SupplierSelector
        suppliers={mockSuppliers}
        value={mockSuppliers[0]}
        onChange={jest.fn()}
      />
    )

    expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
  })

  it('opens dropdown on click', async () => {
    const user = userEvent.setup()

    render(
      <SupplierSelector
        suppliers={mockSuppliers}
        value={null}
        onChange={jest.fn()}
      />
    )

    // Dropdown should not be visible initially
    expect(screen.queryByPlaceholderText('Search suppliers...')).not.toBeInTheDocument()

    // Click to open
    await user.click(screen.getByText('Select a supplier...'))

    // Dropdown search should now be visible
    expect(screen.getByPlaceholderText('Search suppliers...')).toBeInTheDocument()
    expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
    expect(screen.getByText('United Illuminating')).toBeInTheDocument()
    expect(screen.getByText('NextEra Energy')).toBeInTheDocument()
  })

  it('filters suppliers by search input', async () => {
    const user = userEvent.setup()

    render(
      <SupplierSelector
        suppliers={mockSuppliers}
        value={null}
        onChange={jest.fn()}
      />
    )

    await user.click(screen.getByText('Select a supplier...'))
    await user.type(screen.getByPlaceholderText('Search suppliers...'), 'Ever')

    expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
    expect(screen.queryByText('United Illuminating')).not.toBeInTheDocument()
  })

  it('calls onChange when supplier selected', async () => {
    const onChange = jest.fn()
    const user = userEvent.setup()

    render(
      <SupplierSelector
        suppliers={mockSuppliers}
        value={null}
        onChange={onChange}
      />
    )

    await user.click(screen.getByText('Select a supplier...'))
    await user.click(screen.getByText('United Illuminating'))

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ id: '2', name: 'United Illuminating' })
    )
  })

  it('is disabled when disabled prop is true', () => {
    render(
      <SupplierSelector
        suppliers={mockSuppliers}
        value={null}
        onChange={jest.fn()}
        disabled
      />
    )

    const trigger = screen.getByRole('button')
    expect(trigger).toBeDisabled()
  })

  it('shows "No suppliers found" when search has no matches', async () => {
    const user = userEvent.setup()

    render(
      <SupplierSelector
        suppliers={mockSuppliers}
        value={null}
        onChange={jest.fn()}
      />
    )

    await user.click(screen.getByText('Select a supplier...'))
    await user.type(screen.getByPlaceholderText('Search suppliers...'), 'zzzzz')

    expect(screen.getByText('No suppliers found')).toBeInTheDocument()
  })
})
