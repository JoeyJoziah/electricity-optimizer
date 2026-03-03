import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import React from 'react'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

jest.mock('lucide-react', () => ({
  Bell: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="bell-icon" {...props} />,
}))

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// ---------------------------------------------------------------------------
// API client mock — configurable per test
// ---------------------------------------------------------------------------
const mockApiGet = jest.fn()
const mockApiPut = jest.fn()

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: (...args: unknown[]) => mockApiGet(...args),
    put: (...args: unknown[]) => mockApiPut(...args),
  },
}))

// ---------------------------------------------------------------------------
// Default fixture data
// ---------------------------------------------------------------------------
const defaultCountResponse = { unread: 0 }

const defaultNotificationsResponse = {
  notifications: [
    {
      id: 'notif_1',
      type: 'price_alert',
      title: 'Price Alert: Rates dropping',
      body: 'CT rates have dropped below $0.20/kWh',
      created_at: '2026-03-01T10:00:00Z',
    },
    {
      id: 'notif_2',
      type: 'savings',
      title: 'Weekly savings report',
      body: null,
      created_at: '2026-03-01T09:00:00Z',
    },
  ],
  total: 2,
}

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------
import { NotificationBell } from '@/components/layout/NotificationBell'

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        // Disable automatic refetch to prevent unexpected API calls in tests
        refetchInterval: false,
        refetchOnWindowFocus: false,
        refetchOnMount: false,
        staleTime: Infinity,
      },
    },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('NotificationBell', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockApiGet.mockResolvedValue(defaultCountResponse)
    mockApiPut.mockResolvedValue({})
  })

  // --- Bell button rendering ---

  it('renders the bell button', async () => {
    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByRole('button')).toBeInTheDocument()
    })
  })

  it('renders the Bell icon', async () => {
    render(<NotificationBell />, { wrapper: createWrapper() })

    expect(screen.getByTestId('bell-icon')).toBeInTheDocument()
  })

  it('has accessible label "Notifications" when unread count is 0', async () => {
    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Notifications')
    })
  })

  it('has accessible label including unread count when count > 0', async () => {
    mockApiGet.mockResolvedValue({ unread: 3 })

    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Notifications (3 unread)')
    })
  })

  it('starts with aria-expanded false (panel closed)', () => {
    render(<NotificationBell />, { wrapper: createWrapper() })

    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  // --- Unread count badge ---

  it('does not show count badge when unread is 0', async () => {
    mockApiGet.mockResolvedValue({ unread: 0 })

    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.queryByText('0')).not.toBeInTheDocument()
    })
  })

  it('shows unread count badge when there are unread notifications', async () => {
    mockApiGet.mockResolvedValue({ unread: 5 })

    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument()
    })
  })

  it('caps the badge display at "9+" for counts above 9', async () => {
    mockApiGet.mockResolvedValue({ unread: 12 })

    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('9+')).toBeInTheDocument()
    })
  })

  it('shows exact count for counts 1–9', async () => {
    mockApiGet.mockResolvedValue({ unread: 9 })

    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('9')).toBeInTheDocument()
    })
  })

  it('marks the badge span as aria-hidden', async () => {
    mockApiGet.mockResolvedValue({ unread: 2 })

    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      const badge = screen.getByText('2')
      expect(badge).toHaveAttribute('aria-hidden', 'true')
    })
  })

  // --- Panel toggle ---

  it('panel is not visible initially', () => {
    render(<NotificationBell />, { wrapper: createWrapper() })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens the notification panel when bell is clicked', async () => {
    const user = userEvent.setup()
    mockApiGet.mockResolvedValue(defaultCountResponse)

    render(<NotificationBell />, { wrapper: createWrapper() })

    await user.click(screen.getByRole('button'))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Notifications')).toBeInTheDocument()
  })

  it('sets aria-expanded to true when panel opens', async () => {
    const user = userEvent.setup()

    render(<NotificationBell />, { wrapper: createWrapper() })

    await user.click(screen.getByRole('button'))

    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true')
  })

  it('closes the panel when bell is clicked a second time', async () => {
    const user = userEvent.setup()

    render(<NotificationBell />, { wrapper: createWrapper() })

    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await user.click(screen.getByRole('button'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('sets aria-expanded back to false when panel closes', async () => {
    const user = userEvent.setup()

    render(<NotificationBell />, { wrapper: createWrapper() })

    await user.click(screen.getByRole('button'))
    await user.click(screen.getByRole('button'))

    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false')
  })

  // --- Panel content ---

  it('renders the panel heading "Notifications"', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return Promise.resolve(defaultNotificationsResponse)
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    // "Notifications" appears in both the dialog and possibly aria-label;
    // the heading inside the panel has class text-sm font-semibold
    const heading = screen.getByRole('dialog').querySelector('h3')
    expect(heading).toHaveTextContent('Notifications')
  })

  it('shows notification titles when panel opens with data', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return Promise.resolve(defaultNotificationsResponse)
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    await waitFor(() => {
      expect(screen.getByText('Price Alert: Rates dropping')).toBeInTheDocument()
      expect(screen.getByText('Weekly savings report')).toBeInTheDocument()
    })
  })

  it('shows notification body when present', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return Promise.resolve(defaultNotificationsResponse)
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    await waitFor(() => {
      expect(
        screen.getByText('CT rates have dropped below $0.20/kWh')
      ).toBeInTheDocument()
    })
  })

  it('does not render body element when body is null', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return Promise.resolve({
        notifications: [
          {
            id: 'notif_no_body',
            type: 'info',
            title: 'No body notification',
            body: null,
            created_at: '2026-03-01T09:00:00Z',
          },
        ],
        total: 1,
      })
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    await waitFor(() => {
      expect(screen.getByText('No body notification')).toBeInTheDocument()
    })
    // There should be no additional <p> for the body
    const dialog = screen.getByRole('dialog')
    const bodyParagraphs = dialog.querySelectorAll('p.text-xs')
    expect(bodyParagraphs.length).toBe(0)
  })

  it('shows "No new notifications" when list is empty', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return Promise.resolve({ notifications: [], total: 0 })
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    await waitFor(() => {
      expect(screen.getByText('No new notifications')).toBeInTheDocument()
    })
  })

  it('shows "No new notifications" when panel opens before data loads', async () => {
    const user = userEvent.setup()
    // Count resolves quickly; notifications hangs
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return new Promise(() => {}) // never resolves
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    // Before data arrives the list is empty — empty state should show
    expect(screen.getByText('No new notifications')).toBeInTheDocument()
  })

  // --- Mark-as-read mutation ---

  it('calls PUT /notifications/:id/read when a notification is clicked', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return Promise.resolve(defaultNotificationsResponse)
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    await waitFor(() => {
      expect(screen.getByText('Price Alert: Rates dropping')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Price Alert: Rates dropping'))

    await waitFor(() => {
      expect(mockApiPut).toHaveBeenCalledWith('/notifications/notif_1/read', {})
    })
  })

  it('calls PUT with the correct notification id', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return Promise.resolve(defaultNotificationsResponse)
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    await waitFor(() => {
      expect(screen.getByText('Weekly savings report')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Weekly savings report'))

    await waitFor(() => {
      expect(mockApiPut).toHaveBeenCalledWith('/notifications/notif_2/read', {})
    })
  })

  // --- Click outside to close ---

  it('closes the panel when clicking outside the container', async () => {
    const user = userEvent.setup()

    render(
      <div>
        <NotificationBell />
        <div data-testid="outside-element">Outside</div>
      </div>,
      { wrapper: createWrapper() }
    )

    // Open the panel
    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    // Click outside
    await user.click(screen.getByTestId('outside-element'))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('does not close the panel when clicking inside the container', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return Promise.resolve({ notifications: [], total: 0 })
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    expect(screen.getByRole('dialog')).toBeInTheDocument()

    // Click inside the panel — should not close
    await user.click(screen.getByRole('dialog'))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  // --- API calls ---

  it('fetches the unread count from /notifications/count on mount', async () => {
    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/notifications/count')
    })
  })

  it('does not fetch the full notifications list until panel is opened', async () => {
    render(<NotificationBell />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/notifications/count')
    })

    // Notifications list should NOT have been fetched yet
    expect(mockApiGet).not.toHaveBeenCalledWith('/notifications')
  })

  it('fetches the notifications list when panel is opened', async () => {
    const user = userEvent.setup()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/notifications/count') return Promise.resolve(defaultCountResponse)
      return Promise.resolve(defaultNotificationsResponse)
    })

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/notifications')
    })
  })

  // --- Edge cases ---

  it('handles API error for count gracefully (shows 0 unread)', async () => {
    mockApiGet.mockRejectedValue(new Error('Network error'))

    render(<NotificationBell />, { wrapper: createWrapper() })

    // Should not throw; bell renders without badge
    await waitFor(() => {
      expect(screen.getByRole('button')).toBeInTheDocument()
    })
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('renders the dialog with aria-label "Notifications panel"', async () => {
    const user = userEvent.setup()

    render(<NotificationBell />, { wrapper: createWrapper() })
    await user.click(screen.getByRole('button'))

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-label', 'Notifications panel')
  })
})
