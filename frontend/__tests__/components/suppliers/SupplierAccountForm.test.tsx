import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SupplierAccountForm } from '@/components/suppliers/SupplierAccountForm'
import '@testing-library/jest-dom'

describe('SupplierAccountForm', () => {
  const defaultProps = {
    supplierId: 'supplier-1',
    supplierName: 'Eversource Energy',
    onSubmit: jest.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders collapsed "Link Account" button initially', () => {
    render(<SupplierAccountForm {...defaultProps} />)

    expect(screen.getByRole('button', { name: /link account/i })).toBeInTheDocument()
    // Form fields should not be visible
    expect(screen.queryByLabelText(/account number/i)).not.toBeInTheDocument()
  })

  it('expands form on button click', async () => {
    const user = userEvent.setup()
    render(<SupplierAccountForm {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: /link account/i }))

    // Form should now be visible with the supplier name
    expect(screen.getByText(/link your eversource energy account/i)).toBeInTheDocument()
  })

  it('shows cancel button when expanded', async () => {
    const user = userEvent.setup()
    render(<SupplierAccountForm {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: /link account/i }))

    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('collapses form on cancel click', async () => {
    const user = userEvent.setup()
    render(<SupplierAccountForm {...defaultProps} />)

    // Expand
    await user.click(screen.getByRole('button', { name: /link account/i }))
    expect(screen.getByText(/link your eversource energy account/i)).toBeInTheDocument()

    // Collapse
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(screen.queryByText(/link your eversource energy account/i)).not.toBeInTheDocument()
  })

  it('submit button disabled without consent checkbox', async () => {
    const user = userEvent.setup()
    render(<SupplierAccountForm {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: /link account/i }))

    // Type a valid account number but don't check consent
    const accountInput = screen.getByPlaceholderText('e.g., 1234567890')
    await user.type(accountInput, '1234567890')

    // Submit should be disabled (no consent)
    const submitButton = screen.getByRole('button', { name: /^link account$/i })
    expect(submitButton).toBeDisabled()
  })

  it('submit button disabled with invalid account number', async () => {
    const user = userEvent.setup()
    render(<SupplierAccountForm {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: /link account/i }))

    // Type invalid account number (too short)
    const accountInput = screen.getByPlaceholderText('e.g., 1234567890')
    await user.type(accountInput, 'AB')

    // Check consent
    const checkbox = screen.getByRole('checkbox')
    await user.click(checkbox)

    const submitButton = screen.getByRole('button', { name: /^link account$/i })
    expect(submitButton).toBeDisabled()
  })

  it('calls onSubmit with correct data', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()

    render(
      <SupplierAccountForm
        {...defaultProps}
        onSubmit={onSubmit}
        defaultZip="06001"
      />
    )

    // Expand form
    await user.click(screen.getByRole('button', { name: /link account/i }))

    // Fill account number
    await user.type(screen.getByPlaceholderText('e.g., 1234567890'), '9876543210')

    // Check consent
    await user.click(screen.getByRole('checkbox'))

    // Submit
    const submitButton = screen.getByRole('button', { name: /^link account$/i })
    await user.click(submitButton)

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        supplierId: 'supplier-1',
        accountNumber: '9876543210',
        consentGiven: true,
      })
    )
  })

  it('shows error message on submit failure', async () => {
    const onSubmit = jest.fn().mockRejectedValue(new Error('Network error'))
    const user = userEvent.setup()

    render(<SupplierAccountForm {...defaultProps} onSubmit={onSubmit} />)

    await user.click(screen.getByRole('button', { name: /link account/i }))
    await user.type(screen.getByPlaceholderText('e.g., 1234567890'), '1234567890')
    await user.click(screen.getByRole('checkbox'))

    const submitButton = screen.getByRole('button', { name: /^link account$/i })
    await user.click(submitButton)

    expect(await screen.findByText('Network error')).toBeInTheDocument()
  })

  it('shows encryption notice', async () => {
    const user = userEvent.setup()
    render(<SupplierAccountForm {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: /link account/i }))

    expect(screen.getByText(/encrypted with AES-256-GCM/i)).toBeInTheDocument()
  })

  it('pre-fills service ZIP from defaultZip prop', async () => {
    const user = userEvent.setup()
    render(<SupplierAccountForm {...defaultProps} defaultZip="06001" />)

    await user.click(screen.getByRole('button', { name: /link account/i }))

    const zipInput = screen.getByPlaceholderText('e.g., 06001')
    expect(zipInput).toHaveValue('06001')
  })
})
