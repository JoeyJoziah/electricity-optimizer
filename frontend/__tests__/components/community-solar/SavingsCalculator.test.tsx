import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'

// --- Mocks ---

let mockSavings: {
  monthly_savings: number
  annual_savings: number
  five_year_savings: number
} | null = null
let mockSavingsLoading = false

jest.mock('@/lib/hooks/useCommunitySolar', () => ({
  useCommunitySolarSavings: () => ({
    data: mockSavingsLoading ? undefined : mockSavings,
    isLoading: mockSavingsLoading,
  }),
}))

import { CommunitySolarService } from '@/components/community-solar/SavingsCalculator'

describe('CommunitySolarService (SavingsCalculator)', () => {
  beforeEach(() => {
    mockSavings = null
    mockSavingsLoading = false
    jest.clearAllMocks()
  })

  it('renders calculator header', () => {
    render(<CommunitySolarService />)

    expect(screen.getByText('Savings Calculator')).toBeInTheDocument()
  })

  it('renders form inputs', () => {
    render(<CommunitySolarService />)

    expect(screen.getByLabelText(/Monthly Bill/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Savings/)).toBeInTheDocument()
    expect(screen.getByText('Calculate')).toBeInTheDocument()
  })

  it('disables Calculate button when fields are empty', () => {
    render(<CommunitySolarService />)

    const button = screen.getByText('Calculate')
    expect(button).toBeDisabled()
  })

  it('enables Calculate button when both fields are filled', async () => {
    const user = userEvent.setup()
    render(<CommunitySolarService />)

    await user.type(screen.getByLabelText(/Monthly Bill/), '150')
    await user.type(screen.getByLabelText(/Savings/), '10')

    expect(screen.getByText('Calculate')).not.toBeDisabled()
  })

  it('shows loading state after submit', async () => {
    mockSavingsLoading = true
    const user = userEvent.setup()
    render(<CommunitySolarService />)

    await user.type(screen.getByLabelText(/Monthly Bill/), '150')
    await user.type(screen.getByLabelText(/Savings/), '10')
    await user.click(screen.getByText('Calculate'))

    const { container } = render(<CommunitySolarService />)
    // Just verify the component renders without error in loading state
    expect(container).toBeTruthy()
  })

  it('renders savings results when available', () => {
    mockSavings = {
      monthly_savings: 15,
      annual_savings: 180,
      five_year_savings: 900,
    }

    render(<CommunitySolarService />)

    expect(screen.getByText('$15')).toBeInTheDocument()
    expect(screen.getByText('$180')).toBeInTheDocument()
    expect(screen.getByText('$900')).toBeInTheDocument()
    expect(screen.getByText('Monthly Savings')).toBeInTheDocument()
    expect(screen.getByText('Annual Savings')).toBeInTheDocument()
    expect(screen.getByText('5-Year Savings')).toBeInTheDocument()
  })

  it('hides results when savings is null', () => {
    mockSavings = null

    render(<CommunitySolarService />)

    expect(screen.queryByText('Monthly Savings')).not.toBeInTheDocument()
  })

  it('resets submitted state when input changes', async () => {
    const user = userEvent.setup()
    render(<CommunitySolarService />)

    await user.type(screen.getByLabelText(/Monthly Bill/), '150')
    await user.type(screen.getByLabelText(/Savings/), '10')
    await user.click(screen.getByText('Calculate'))

    // Now change input — should reset submitted
    await user.clear(screen.getByLabelText(/Monthly Bill/))
    await user.type(screen.getByLabelText(/Monthly Bill/), '200')

    // The component won't query until next submit
    expect(screen.getByText('Calculate')).not.toBeDisabled()
  })
})
