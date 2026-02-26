import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EmailConnectionFlow } from '@/components/connections/EmailConnectionFlow'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  Mail: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-mail" {...props} />,
  AlertCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-alert" {...props} />,
  CheckCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-check" {...props} />,
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-loader" {...props} />,
  Search: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-search" {...props} />,
  FileText: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-filetext" {...props} />,
}))

const mockFetch = global.fetch as jest.Mock

// Mock window.location
const originalLocation = window.location

describe('EmailConnectionFlow', () => {
  const defaultProps = {
    onComplete: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockFetch.mockReset()

    // Reset window.location.search
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, search: '', href: '' },
    })
  })

  afterAll(() => {
    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    })
  })

  it('renders the email connection form heading', () => {
    render(<EmailConnectionFlow {...defaultProps} />)

    expect(screen.getByText('Connect Email Inbox')).toBeInTheDocument()
    expect(
      screen.getByText(/we will scan your inbox for utility bills/i)
    ).toBeInTheDocument()
  })

  it('renders Gmail and Outlook provider options', () => {
    render(<EmailConnectionFlow {...defaultProps} />)

    expect(screen.getByText('Gmail')).toBeInTheDocument()
    expect(screen.getByText('Google Account')).toBeInTheDocument()
    expect(screen.getByText('Outlook')).toBeInTheDocument()
    expect(screen.getByText('Microsoft Account')).toBeInTheDocument()
  })

  it('renders privacy info section', () => {
    render(<EmailConnectionFlow {...defaultProps} />)

    expect(screen.getByText('Privacy-first scanning')).toBeInTheDocument()
    expect(
      screen.getByText(/we only scan for utility-related emails/i)
    ).toBeInTheDocument()
  })

  it('renders consent checkbox', () => {
    render(<EmailConnectionFlow {...defaultProps} />)

    expect(
      screen.getByText(
        /i consent to electricity optimizer scanning my inbox/i
      )
    ).toBeInTheDocument()
  })

  it('shows "Connect Email" button text when no provider is selected', () => {
    render(<EmailConnectionFlow {...defaultProps} />)

    expect(
      screen.getByRole('button', { name: /connect email/i })
    ).toBeInTheDocument()
  })

  it('connect button is disabled when no provider selected', () => {
    render(<EmailConnectionFlow {...defaultProps} />)

    const button = screen.getByRole('button', { name: /connect email/i })
    expect(button).toBeDisabled()
  })

  it('updates button text when Gmail is selected', async () => {
    const user = userEvent.setup()
    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(screen.getByText('Gmail'))

    expect(
      screen.getByRole('button', { name: /connect gmail/i })
    ).toBeInTheDocument()
  })

  it('updates button text when Outlook is selected', async () => {
    const user = userEvent.setup()
    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(screen.getByText('Outlook'))

    expect(
      screen.getByRole('button', { name: /connect outlook/i })
    ).toBeInTheDocument()
  })

  it('connect button is disabled when provider selected but consent unchecked', async () => {
    const user = userEvent.setup()
    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(screen.getByText('Gmail'))

    const button = screen.getByRole('button', { name: /connect gmail/i })
    expect(button).toBeDisabled()
  })

  it('connect button is enabled when provider selected and consent checked', async () => {
    const user = userEvent.setup()
    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(screen.getByText('Gmail'))
    await user.click(screen.getByRole('checkbox'))

    const button = screen.getByRole('button', { name: /connect gmail/i })
    expect(button).not.toBeDisabled()
  })

  it('shows 403 upgrade error when API returns forbidden', async () => {
    const user = userEvent.setup()
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'Upgrade required' }),
    })

    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(screen.getByText('Gmail'))
    await user.click(screen.getByRole('checkbox'))
    await user.click(
      screen.getByRole('button', { name: /connect gmail/i })
    )

    await waitFor(() => {
      expect(
        screen.getByText(
          /email connections are available on pro and business plans/i
        )
      ).toBeInTheDocument()
    })
  })

  it('shows generic error on non-403 failure', async () => {
    const user = userEvent.setup()
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: 'Internal error' }),
    })

    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(screen.getByText('Outlook'))
    await user.click(screen.getByRole('checkbox'))
    await user.click(
      screen.getByRole('button', { name: /connect outlook/i })
    )

    await waitFor(() => {
      expect(screen.getByText('Internal error')).toBeInTheDocument()
    })
  })

  it('shows network error on fetch failure', async () => {
    const user = userEvent.setup()
    mockFetch.mockRejectedValueOnce(new Error('Network failure'))

    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(screen.getByText('Gmail'))
    await user.click(screen.getByRole('checkbox'))
    await user.click(
      screen.getByRole('button', { name: /connect gmail/i })
    )

    await waitFor(() => {
      expect(
        screen.getByText(/network error. please check your connection/i)
      ).toBeInTheDocument()
    })
  })

  it('shows connected state when URL has connected param', () => {
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        ...originalLocation,
        search: '?connected=conn-123',
        href: 'http://localhost:3000?connected=conn-123',
      },
    })

    render(<EmailConnectionFlow {...defaultProps} />)

    expect(
      screen.getByText('Email Connected Successfully')
    ).toBeInTheDocument()
    expect(
      screen.getByText(/your email account is linked/i)
    ).toBeInTheDocument()
  })

  it('shows scan inbox button in connected state', () => {
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        ...originalLocation,
        search: '?connected=conn-123',
        href: 'http://localhost:3000?connected=conn-123',
      },
    })

    render(<EmailConnectionFlow {...defaultProps} />)

    expect(
      screen.getByRole('button', { name: /scan inbox/i })
    ).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
  })

  it('calls onComplete when Done is clicked in connected state', async () => {
    const user = userEvent.setup()
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        ...originalLocation,
        search: '?connected=conn-123',
        href: 'http://localhost:3000?connected=conn-123',
      },
    })

    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(screen.getByText('Done'))
    expect(defaultProps.onComplete).toHaveBeenCalled()
  })

  it('scans inbox and displays scan results', async () => {
    const user = userEvent.setup()
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        ...originalLocation,
        search: '?connected=conn-123',
        href: 'http://localhost:3000?connected=conn-123',
      },
    })

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          total_emails_scanned: 150,
          utility_bills_found: 3,
          bills: [
            { subject: 'Eversource Bill - January 2026', sender: 'billing@eversource.com', date: '2026-01-15', amount: 142.50 },
            { subject: 'Eversource Bill - December 2025', sender: 'billing@eversource.com', date: '2025-12-15', amount: 128.00 },
            { subject: 'Eversource Bill - November 2025', sender: 'billing@eversource.com', date: '2025-11-15', amount: 98.50 },
          ],
        }),
    })

    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(
      screen.getByRole('button', { name: /scan inbox/i })
    )

    await waitFor(() => {
      expect(screen.getByText('Scan complete')).toBeInTheDocument()
    })

    expect(
      screen.getByText(/scanned 150 emails and found 3 utility bills/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText('Eversource Bill - January 2026')
    ).toBeInTheDocument()
  })

  it('shows empty state when no bills are found during scan', async () => {
    const user = userEvent.setup()
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        ...originalLocation,
        search: '?connected=conn-123',
        href: 'http://localhost:3000?connected=conn-123',
      },
    })

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          total_emails_scanned: 100,
          utility_bills_found: 0,
          bills: [],
        }),
    })

    render(<EmailConnectionFlow {...defaultProps} />)

    await user.click(
      screen.getByRole('button', { name: /scan inbox/i })
    )

    await waitFor(() => {
      expect(
        screen.getByText(/no utility bills found in your inbox/i)
      ).toBeInTheDocument()
    })
  })
})
