import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SetSupplierDialog } from '@/components/suppliers/SetSupplierDialog'
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
]

describe('SetSupplierDialog', () => {
  it('renders supplier list', () => {
    render(
      <SetSupplierDialog
        suppliers={mockSuppliers}
        onSelect={jest.fn()}
        onCancel={jest.fn()}
      />
    )

    expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
    expect(screen.getByText('United Illuminating')).toBeInTheDocument()
  })

  it('calls onCancel when cancel clicked', async () => {
    const onCancel = jest.fn()
    const user = userEvent.setup()

    render(
      <SetSupplierDialog
        suppliers={mockSuppliers}
        onSelect={jest.fn()}
        onCancel={onCancel}
      />
    )

    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('confirm button disabled when no supplier selected', () => {
    render(
      <SetSupplierDialog
        suppliers={mockSuppliers}
        onSelect={jest.fn()}
        onCancel={jest.fn()}
      />
    )

    const confirmButton = screen.getByRole('button', { name: /set as my supplier/i })
    expect(confirmButton).toBeDisabled()
  })

  it('calls onSelect with selected supplier on confirm', async () => {
    const onSelect = jest.fn()
    const user = userEvent.setup()

    render(
      <SetSupplierDialog
        suppliers={mockSuppliers}
        onSelect={onSelect}
        onCancel={jest.fn()}
      />
    )

    // Click first supplier to select it
    await user.click(screen.getByText('Eversource Energy'))

    // Click confirm
    const confirmButton = screen.getByRole('button', { name: /set as my supplier/i })
    expect(confirmButton).not.toBeDisabled()
    await user.click(confirmButton)

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: '1', name: 'Eversource Energy' })
    )
  })

  it('shows loading state when isLoading is true', () => {
    render(
      <SetSupplierDialog
        suppliers={mockSuppliers}
        onSelect={jest.fn()}
        onCancel={jest.fn()}
        isLoading
      />
    )

    const confirmButton = screen.getByRole('button', { name: /set as my supplier/i })
    expect(confirmButton).toBeDisabled()
  })

  it('shows green badge for green energy suppliers', () => {
    render(
      <SetSupplierDialog
        suppliers={mockSuppliers}
        onSelect={jest.fn()}
        onCancel={jest.fn()}
      />
    )

    expect(screen.getByText(/green/i)).toBeInTheDocument()
  })
})
