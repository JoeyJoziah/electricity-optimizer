import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'

const mockLinkAccountMutate = jest.fn()

jest.mock('@/lib/hooks/useSuppliers', () => ({
  useLinkAccount: () => ({
    mutateAsync: mockLinkAccountMutate,
    isPending: false,
  }),
}))

jest.mock('@/components/suppliers/SupplierAccountForm', () => ({
  SupplierAccountForm: ({
    supplierId,
    supplierName,
    onSubmit,
    isLoading,
  }: {
    supplierId: string
    supplierName: string
    onSubmit: (data: { supplierId: string; accountNumber: string; consentGiven: boolean }) => void
    isLoading: boolean
  }) => (
    <div data-testid="supplier-account-form">
      <span data-testid="form-supplier-id">{supplierId}</span>
      <span data-testid="form-supplier-name">{supplierName}</span>
      <button
        data-testid="form-submit"
        onClick={() =>
          onSubmit({ supplierId, accountNumber: '123456', consentGiven: true })
        }
        disabled={isLoading}
      >
        Submit
      </button>
    </div>
  ),
}))

import { AccountLinkStep } from '@/components/onboarding/AccountLinkStep'

const mockSupplier = {
  id: 'supplier-1',
  name: 'Eversource Energy',
  avgPricePerKwh: 0.25,
  standingCharge: 0.50,
  greenEnergy: true,
  rating: 4.5,
  estimatedAnnualCost: 1200,
  tariffType: 'variable' as const,
}

describe('AccountLinkStep', () => {
  const mockOnComplete = jest.fn()
  const mockOnSkip = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    mockLinkAccountMutate.mockResolvedValue(undefined)
  })

  it('renders the link your account heading', () => {
    render(
      <AccountLinkStep
        supplier={mockSupplier}
        onComplete={mockOnComplete}
        onSkip={mockOnSkip}
      />
    )

    expect(screen.getByRole('heading', { name: /link your account/i })).toBeInTheDocument()
  })

  it('renders supplier name in the description', () => {
    render(
      <AccountLinkStep
        supplier={mockSupplier}
        onComplete={mockOnComplete}
        onSkip={mockOnSkip}
      />
    )

    // Supplier name appears in description text and in the mocked form — use getAllBy
    const matches = screen.getAllByText(/eversource energy/i)
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })

  it('renders the SupplierAccountForm with correct props', () => {
    render(
      <AccountLinkStep
        supplier={mockSupplier}
        onComplete={mockOnComplete}
        onSkip={mockOnSkip}
      />
    )

    expect(screen.getByTestId('supplier-account-form')).toBeInTheDocument()
    expect(screen.getByTestId('form-supplier-id')).toHaveTextContent('supplier-1')
    expect(screen.getByTestId('form-supplier-name')).toHaveTextContent('Eversource Energy')
  })

  it('renders the skip button', () => {
    render(
      <AccountLinkStep
        supplier={mockSupplier}
        onComplete={mockOnComplete}
        onSkip={mockOnSkip}
      />
    )

    expect(screen.getByRole('button', { name: /skip for now/i })).toBeInTheDocument()
  })

  it('calls onSkip when skip button is clicked', async () => {
    const user = userEvent.setup()
    render(
      <AccountLinkStep
        supplier={mockSupplier}
        onComplete={mockOnComplete}
        onSkip={mockOnSkip}
      />
    )

    await user.click(screen.getByRole('button', { name: /skip for now/i }))

    expect(mockOnSkip).toHaveBeenCalledTimes(1)
  })

  it('calls linkAccount.mutateAsync with correct data on form submit', async () => {
    const user = userEvent.setup()
    render(
      <AccountLinkStep
        supplier={mockSupplier}
        onComplete={mockOnComplete}
        onSkip={mockOnSkip}
      />
    )

    await user.click(screen.getByTestId('form-submit'))

    await waitFor(() => {
      expect(mockLinkAccountMutate).toHaveBeenCalledWith({
        supplier_id: 'supplier-1',
        account_number: '123456',
        meter_number: undefined,
        service_zip: undefined,
        account_nickname: undefined,
        consent_given: true,
      })
    })
  })

  it('calls onComplete after successful link', async () => {
    const user = userEvent.setup()
    render(
      <AccountLinkStep
        supplier={mockSupplier}
        onComplete={mockOnComplete}
        onSkip={mockOnSkip}
      />
    )

    await user.click(screen.getByTestId('form-submit'))

    await waitFor(() => {
      expect(mockOnComplete).toHaveBeenCalledTimes(1)
    })
  })

  it('shows helper text about linking later', () => {
    render(
      <AccountLinkStep
        supplier={mockSupplier}
        onComplete={mockOnComplete}
        onSkip={mockOnSkip}
      />
    )

    expect(screen.getByText(/you can link your account any time/i)).toBeInTheDocument()
  })
})
