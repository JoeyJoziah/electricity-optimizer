import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Header } from '@/components/layout/Header'
import '@testing-library/jest-dom'

// Mock usePrices hook
const mockRefreshPrices = jest.fn()
jest.mock('@/lib/hooks/usePrices', () => ({
  useRefreshPrices: () => mockRefreshPrices,
}))

// Mock NotificationBell to avoid QueryClientProvider requirement
jest.mock('@/components/layout/NotificationBell', () => ({
  NotificationBell: () => <div data-testid="notification-bell">notifications</div>,
}))

// Mock sidebar context
const mockToggle = jest.fn()
const mockClose = jest.fn()
jest.mock('@/lib/contexts/sidebar-context', () => ({
  useSidebar: () => ({
    isOpen: false,
    toggle: mockToggle,
    close: mockClose,
  }),
}))

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  Bell: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="bell-icon" {...props} />,
  RefreshCw: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="refresh-icon" {...props} />,
  Menu: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="menu-icon" {...props} />,
}))

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock Button and Badge components
jest.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button onClick={onClick} disabled={disabled} {...props}>{children}</button>
  ),
}))

jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.HTMLAttributes<HTMLSpanElement>) => (
    <span {...props}>{children}</span>
  ),
}))

describe('Header', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('renders the page title', () => {
    render(<Header title="Dashboard" />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('renders with different title prop', () => {
    render(<Header title="Prices" />)

    expect(screen.getByText('Prices')).toBeInTheDocument()
  })

  it('renders the mobile menu button', () => {
    render(<Header title="Dashboard" />)

    expect(screen.getByLabelText('Open menu')).toBeInTheDocument()
  })

  it('calls sidebar toggle when mobile menu button is clicked (no onMenuClick prop)', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

    render(<Header title="Dashboard" />)

    await user.click(screen.getByLabelText('Open menu'))

    expect(mockToggle).toHaveBeenCalledTimes(1)
  })

  it('calls onMenuClick when provided as prop (backward compat)', async () => {
    const onMenuClick = jest.fn()
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

    render(<Header title="Dashboard" onMenuClick={onMenuClick} />)

    await user.click(screen.getByLabelText('Open menu'))

    expect(onMenuClick).toHaveBeenCalledTimes(1)
    // Should NOT call sidebar toggle when onMenuClick prop is provided
    expect(mockToggle).not.toHaveBeenCalled()
  })

  it('renders the realtime live indicator', () => {
    render(<Header title="Dashboard" />)

    expect(screen.getByText('Live')).toBeInTheDocument()
  })

  it('renders the refresh data button', () => {
    render(<Header title="Dashboard" />)

    expect(screen.getByLabelText('Refresh data')).toBeInTheDocument()
  })

  it('calls refreshPrices when refresh button is clicked', async () => {
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
    render(<Header title="Dashboard" />)

    await user.click(screen.getByLabelText('Refresh data'))

    expect(mockRefreshPrices).toHaveBeenCalledTimes(1)
  })

  it('renders the notification bell component', () => {
    render(<Header title="Dashboard" />)

    expect(screen.getByTestId('notification-bell')).toBeInTheDocument()
  })

  it('renders as a header element', () => {
    render(<Header title="Dashboard" />)

    expect(screen.getByRole('banner')).toBeInTheDocument()
  })
})
