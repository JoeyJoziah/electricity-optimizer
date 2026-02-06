import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SupplierCard } from '@/components/suppliers/SupplierCard'
import '@testing-library/jest-dom'

const mockSupplier = {
  id: '1',
  name: 'Octopus Energy',
  logo: '/logos/octopus.png',
  avgPricePerKwh: 0.25,
  standingCharge: 0.50,
  greenEnergy: true,
  rating: 4.5,
  estimatedAnnualCost: 1200,
  tariffType: 'variable' as const,
  features: ['Smart meter compatible', '100% renewable'],
}

describe('SupplierCard', () => {
  it('renders supplier information correctly', () => {
    render(<SupplierCard supplier={mockSupplier} />)

    expect(screen.getByText('Octopus Energy')).toBeInTheDocument()
    expect(screen.getByText(/0\.25/)).toBeInTheDocument()
    expect(screen.getByText(/1,200/)).toBeInTheDocument()
  })

  it('displays green energy badge for renewable suppliers', () => {
    render(<SupplierCard supplier={mockSupplier} />)

    expect(screen.getByText(/green energy/i)).toBeInTheDocument()
  })

  it('does not display green energy badge for non-renewable suppliers', () => {
    const nonGreenSupplier = { ...mockSupplier, greenEnergy: false }
    render(<SupplierCard supplier={nonGreenSupplier} />)

    expect(screen.queryByText(/green energy/i)).not.toBeInTheDocument()
  })

  it('shows star rating correctly', () => {
    render(<SupplierCard supplier={mockSupplier} />)

    expect(screen.getByText('4.5')).toBeInTheDocument()
  })

  it('highlights current supplier with badge', () => {
    render(<SupplierCard supplier={mockSupplier} isCurrent />)

    expect(screen.getByText(/current supplier/i)).toBeInTheDocument()
  })

  it('shows estimated savings compared to current cost', () => {
    render(<SupplierCard supplier={mockSupplier} currentAnnualCost={1500} />)

    // Should show saving of 300 (1500 - 1200)
    expect(screen.getByText(/save/i)).toBeInTheDocument()
    expect(screen.getByText(/300/)).toBeInTheDocument()
  })

  it('does not show savings when more expensive than current', () => {
    render(<SupplierCard supplier={mockSupplier} currentAnnualCost={1000} />)

    expect(screen.queryByText(/save/i)).not.toBeInTheDocument()
  })

  it('calls onSelect when switch button clicked', async () => {
    const onSelect = jest.fn()
    const user = userEvent.setup()

    render(<SupplierCard supplier={mockSupplier} onSelect={onSelect} />)

    await user.click(screen.getByRole('button', { name: /switch/i }))

    expect(onSelect).toHaveBeenCalledWith(mockSupplier)
  })

  it('shows detailed tariff information when showDetails is true', () => {
    render(<SupplierCard supplier={mockSupplier} showDetails />)

    expect(screen.getByText(/standing charge/i)).toBeInTheDocument()
    expect(screen.getByText(/0\.50/)).toBeInTheDocument()
  })

  it('displays tariff type badge', () => {
    render(<SupplierCard supplier={mockSupplier} />)

    expect(screen.getByText(/variable/i)).toBeInTheDocument()
  })

  it('shows features list when available', () => {
    render(<SupplierCard supplier={mockSupplier} showDetails />)

    expect(screen.getByText(/smart meter compatible/i)).toBeInTheDocument()
    expect(screen.getByText(/100% renewable/i)).toBeInTheDocument()
  })

  it('hides switch button for current supplier', () => {
    render(<SupplierCard supplier={mockSupplier} isCurrent />)

    expect(screen.queryByRole('button', { name: /switch/i })).not.toBeInTheDocument()
  })

  it('displays exit fee warning when present', () => {
    const supplierWithExitFee = { ...mockSupplier, exitFee: 50 }
    render(<SupplierCard supplier={supplierWithExitFee} showDetails />)

    expect(screen.getByText(/exit fee/i)).toBeInTheDocument()
    expect(screen.getByText(/50/)).toBeInTheDocument()
  })

  it('is keyboard accessible', async () => {
    const onSelect = jest.fn()
    const user = userEvent.setup()

    render(<SupplierCard supplier={mockSupplier} onSelect={onSelect} />)

    const switchButton = screen.getByRole('button', { name: /switch/i })
    switchButton.focus()

    await user.keyboard('{Enter}')

    expect(onSelect).toHaveBeenCalledWith(mockSupplier)
  })

  it('renders supplier logo when provided', () => {
    render(<SupplierCard supplier={mockSupplier} />)

    const logo = screen.getByAltText(/octopus energy logo/i)
    expect(logo).toBeInTheDocument()
  })

  it('renders placeholder when logo is not provided', () => {
    const supplierWithoutLogo = { ...mockSupplier, logo: undefined }
    render(<SupplierCard supplier={supplierWithoutLogo} />)

    expect(screen.getByTestId('supplier-logo-placeholder')).toBeInTheDocument()
  })
})
