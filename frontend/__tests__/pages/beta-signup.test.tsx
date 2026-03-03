import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'
import BetaSignupPage from '@/app/(app)/beta-signup/page'

const mockFetch = global.fetch as jest.Mock

describe('BetaSignupPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({}) })
  })

  it('renders the Join Beta Program heading', () => {
    render(<BetaSignupPage />)
    expect(
      screen.getByRole('heading', { name: /join the beta program/i })
    ).toBeInTheDocument()
  })

  it('renders the subtitle', () => {
    render(<BetaSignupPage />)
    expect(screen.getByText(/save \$200\+/i)).toBeInTheDocument()
  })

  it('renders Personal Information section', () => {
    render(<BetaSignupPage />)
    expect(screen.getByRole('heading', { name: /personal information/i })).toBeInTheDocument()
  })

  it('renders email, name, and postcode fields', () => {
    render(<BetaSignupPage />)
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/zip code/i)).toBeInTheDocument()
  })

  it('renders Current Electricity Setup section', () => {
    render(<BetaSignupPage />)
    expect(screen.getByRole('heading', { name: /current electricity setup/i })).toBeInTheDocument()
  })

  it('renders current supplier select', () => {
    render(<BetaSignupPage />)
    expect(screen.getByLabelText(/current supplier/i)).toBeInTheDocument()
  })

  it('renders monthly bill range select', () => {
    render(<BetaSignupPage />)
    expect(screen.getByLabelText(/approximate monthly bill/i)).toBeInTheDocument()
  })

  it('renders hear about us select', () => {
    render(<BetaSignupPage />)
    expect(screen.getByLabelText(/how did you hear/i)).toBeInTheDocument()
  })

  it('renders beta agreement checkbox', () => {
    render(<BetaSignupPage />)
    expect(screen.getByLabelText(/I agree to participate/i)).toBeInTheDocument()
  })

  it('renders the Privacy Policy link', () => {
    render(<BetaSignupPage />)
    const privacyLink = screen.getByRole('link', { name: /privacy policy/i })
    expect(privacyLink).toHaveAttribute('href', '/privacy')
  })

  it('renders the Terms of Service link', () => {
    render(<BetaSignupPage />)
    const termsLink = screen.getByRole('link', { name: /terms of service/i })
    expect(termsLink).toHaveAttribute('href', '/terms')
  })

  it('renders the submit button', () => {
    render(<BetaSignupPage />)
    expect(screen.getByRole('button', { name: /join beta program/i })).toBeInTheDocument()
  })

  it('renders the benefits section', () => {
    render(<BetaSignupPage />)
    expect(screen.getByRole('heading', { name: /what you'll get/i })).toBeInTheDocument()
    expect(screen.getByText('Save Money')).toBeInTheDocument()
    expect(screen.getByText('AI-Powered')).toBeInTheDocument()
    expect(screen.getByText('Auto-Switch')).toBeInTheDocument()
  })

  it('submits the form and shows success state', async () => {
    const user = userEvent.setup()
    render(<BetaSignupPage />)

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com')
    await user.type(screen.getByLabelText(/full name/i), 'Jane Smith')
    await user.type(screen.getByLabelText(/zip code/i), '06510')
    await user.selectOptions(screen.getByLabelText(/current supplier/i), 'Eversource Energy')
    await user.selectOptions(screen.getByLabelText(/approximate monthly bill/i), '$75-$150')
    await user.selectOptions(screen.getByLabelText(/how did you hear/i), 'Reddit')
    await user.click(screen.getByLabelText(/I agree to participate/i))
    await user.click(screen.getByRole('button', { name: /join beta program/i }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /you're on the list/i })).toBeInTheDocument()
    })
  })

  it('POSTs to /api/beta-signup on submit', async () => {
    const user = userEvent.setup()
    render(<BetaSignupPage />)

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com')
    await user.type(screen.getByLabelText(/full name/i), 'Test User')
    await user.type(screen.getByLabelText(/zip code/i), '10001')
    await user.selectOptions(screen.getByLabelText(/current supplier/i), 'Other')
    await user.selectOptions(screen.getByLabelText(/approximate monthly bill/i), '$75-$150')
    await user.selectOptions(screen.getByLabelText(/how did you hear/i), 'Twitter')
    await user.click(screen.getByLabelText(/I agree to participate/i))
    await user.click(screen.getByRole('button', { name: /join beta program/i }))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/beta-signup', expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }))
    })
  })

  it('shows error message when API returns non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false })
    const user = userEvent.setup()
    render(<BetaSignupPage />)

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com')
    await user.type(screen.getByLabelText(/full name/i), 'Jane')
    await user.type(screen.getByLabelText(/zip code/i), '06510')
    await user.selectOptions(screen.getByLabelText(/current supplier/i), 'Other')
    await user.selectOptions(screen.getByLabelText(/approximate monthly bill/i), '<$75')
    await user.selectOptions(screen.getByLabelText(/how did you hear/i), 'Friend')
    await user.click(screen.getByLabelText(/I agree to participate/i))
    await user.click(screen.getByRole('button', { name: /join beta program/i }))

    await waitFor(() => {
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    })
  })

  it('shows what happens next list in success state', async () => {
    const user = userEvent.setup()
    render(<BetaSignupPage />)

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com')
    await user.type(screen.getByLabelText(/full name/i), 'Jane')
    await user.type(screen.getByLabelText(/zip code/i), '06510')
    await user.selectOptions(screen.getByLabelText(/current supplier/i), 'Other')
    await user.selectOptions(screen.getByLabelText(/approximate monthly bill/i), '<$75')
    await user.selectOptions(screen.getByLabelText(/how did you hear/i), 'Friend')
    await user.click(screen.getByLabelText(/I agree to participate/i))
    await user.click(screen.getByRole('button', { name: /join beta program/i }))

    await waitFor(() => {
      expect(screen.getByText(/what happens next/i)).toBeInTheDocument()
      expect(screen.getByText(/welcome email within 24 hours/i)).toBeInTheDocument()
    })
  })
})
