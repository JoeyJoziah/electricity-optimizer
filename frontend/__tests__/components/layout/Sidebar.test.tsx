import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Sidebar } from '@/components/layout/Sidebar'
import '@testing-library/jest-dom'

// Track the mock pathname for changing it between tests
let mockPathname = '/dashboard'

// Mock next/navigation
jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}))

// Mock NotificationBell to avoid QueryClientProvider requirement
jest.mock('@/components/layout/NotificationBell', () => ({
  NotificationBell: () => <div data-testid="notification-bell-sidebar">notifications</div>,
}))

// Mock next/link
jest.mock('next/link', () => {
  const MockLink = ({ children, href, className, onClick, ...props }: { children: React.ReactNode; href: string; className?: string; onClick?: () => void }) => (
    <a href={href} className={className} onClick={onClick} {...props}>{children}</a>
  )
  MockLink.displayName = 'MockLink'
  return MockLink
})

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock useAuth hook (Neon Auth via Better Auth)
jest.mock('@/lib/hooks/useAuth', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    signIn: jest.fn(),
    signUp: jest.fn(),
    signOut: jest.fn(),
    signInWithGoogle: jest.fn(),
    signInWithGitHub: jest.fn(),
    sendMagicLink: jest.fn(),
  }),
}))

// Sidebar context mock values
const mockClose = jest.fn()
const mockToggle = jest.fn()
let mockIsOpen = false

jest.mock('@/lib/contexts/sidebar-context', () => ({
  useSidebar: () => ({
    isOpen: mockIsOpen,
    toggle: mockToggle,
    close: mockClose,
  }),
}))

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  LayoutDashboard: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-dashboard" {...props} />,
  TrendingUp: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-prices" {...props} />,
  Flame: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-gas-rates" {...props} />,
  Sun: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-solar" {...props} />,
  Building2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-suppliers" {...props} />,
  Link2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-connections" {...props} />,
  Calendar: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-optimize" {...props} />,
  Bell: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-alerts" {...props} />,
  Bot: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-assistant" {...props} />,
  Settings: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-settings" {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-zap" {...props} />,
  Fuel: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-fuel" {...props} />,
  Droplets: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-droplets" {...props} />,
  Waves: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-waves" {...props} />,
  BarChart3: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-analytics" {...props} />,
  LogOut: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-logout" {...props} />,
  User: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-user" {...props} />,
  X: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-close" {...props} />,
}))

describe('Sidebar', () => {
  beforeEach(() => {
    mockPathname = '/dashboard'
    mockIsOpen = false
    jest.clearAllMocks()
  })

  it('renders the brand name', () => {
    render(<Sidebar />)

    expect(screen.getByText('Electricity Optimizer')).toBeInTheDocument()
  })

  it('renders the Zap logo icon', () => {
    render(<Sidebar />)

    expect(screen.getByTestId('icon-zap')).toBeInTheDocument()
  })

  it('renders all 14 navigation items', () => {
    render(<Sidebar />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Prices')).toBeInTheDocument()
    expect(screen.getByText('Gas Rates')).toBeInTheDocument()
    expect(screen.getByText('Heating Oil')).toBeInTheDocument()
    expect(screen.getByText('Propane')).toBeInTheDocument()
    expect(screen.getByText('Water')).toBeInTheDocument()
    expect(screen.getByText('Solar')).toBeInTheDocument()
    expect(screen.getByText('Suppliers')).toBeInTheDocument()
    expect(screen.getByText('Connections')).toBeInTheDocument()
    expect(screen.getByText('Optimize')).toBeInTheDocument()
    expect(screen.getByText('Analytics')).toBeInTheDocument()
    expect(screen.getByText('Alerts')).toBeInTheDocument()
    expect(screen.getByText('Assistant')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('renders navigation links with correct hrefs', () => {
    render(<Sidebar />)

    expect(screen.getByText('Dashboard').closest('a')).toHaveAttribute('href', '/dashboard')
    expect(screen.getByText('Prices').closest('a')).toHaveAttribute('href', '/prices')
    expect(screen.getByText('Gas Rates').closest('a')).toHaveAttribute('href', '/gas-rates')
    expect(screen.getByText('Heating Oil').closest('a')).toHaveAttribute('href', '/heating-oil')
    expect(screen.getByText('Propane').closest('a')).toHaveAttribute('href', '/propane')
    expect(screen.getByText('Water').closest('a')).toHaveAttribute('href', '/water')
    expect(screen.getByText('Solar').closest('a')).toHaveAttribute('href', '/community-solar')
    expect(screen.getByText('Suppliers').closest('a')).toHaveAttribute('href', '/suppliers')
    expect(screen.getByText('Connections').closest('a')).toHaveAttribute('href', '/connections')
    expect(screen.getByText('Optimize').closest('a')).toHaveAttribute('href', '/optimize')
    expect(screen.getByText('Analytics').closest('a')).toHaveAttribute('href', '/analytics')
    expect(screen.getByText('Alerts').closest('a')).toHaveAttribute('href', '/alerts')
    expect(screen.getByText('Assistant').closest('a')).toHaveAttribute('href', '/assistant')
    expect(screen.getByText('Settings').closest('a')).toHaveAttribute('href', '/settings')
  })

  it('highlights the active Dashboard route', () => {
    mockPathname = '/dashboard'
    render(<Sidebar />)

    const dashboardLink = screen.getByText('Dashboard').closest('a')
    expect(dashboardLink?.className).toContain('bg-primary-50')
  })

  it('highlights the active Prices route', () => {
    mockPathname = '/prices'
    render(<Sidebar />)

    const pricesLink = screen.getByText('Prices').closest('a')
    expect(pricesLink?.className).toContain('bg-primary-50')

    // Others should not be active
    const dashboardLink = screen.getByText('Dashboard').closest('a')
    expect(dashboardLink?.className).not.toContain('bg-primary-50')
  })

  it('highlights the active Settings route', () => {
    mockPathname = '/settings'
    render(<Sidebar />)

    const settingsLink = screen.getByText('Settings').closest('a')
    expect(settingsLink?.className).toContain('bg-primary-50')
  })

  it('highlights the active Alerts route', () => {
    mockPathname = '/alerts'
    render(<Sidebar />)

    const alertsLink = screen.getByText('Alerts').closest('a')
    expect(alertsLink?.className).toContain('bg-primary-50')
  })

  it('renders the help/support section in footer', () => {
    render(<Sidebar />)

    expect(screen.getByText('Need help?')).toBeInTheDocument()
    expect(screen.getByText(/documentation or contact support/i)).toBeInTheDocument()
  })

  it('renders as an aside element', () => {
    render(<Sidebar />)

    expect(screen.getByRole('complementary')).toBeInTheDocument()
  })

  it('renders a nav element for navigation', () => {
    render(<Sidebar />)

    expect(screen.getByRole('navigation')).toBeInTheDocument()
  })

  describe('mobile sidebar', () => {
    it('does not render mobile overlay when closed', () => {
      mockIsOpen = false
      render(<Sidebar />)

      expect(screen.queryByLabelText('Close sidebar')).not.toBeInTheDocument()
    })

    it('renders mobile overlay and close button when open', () => {
      mockIsOpen = true
      render(<Sidebar />)

      expect(screen.getByLabelText('Close sidebar')).toBeInTheDocument()
    })

    it('calls close when close button is clicked', async () => {
      mockIsOpen = true
      const user = userEvent.setup()
      render(<Sidebar />)

      // close is called once on mount (useEffect with pathname dep), then once on click
      const callsBefore = mockClose.mock.calls.length
      await user.click(screen.getByLabelText('Close sidebar'))

      expect(mockClose.mock.calls.length - callsBefore).toBe(1)
    })

    it('calls close when backdrop is clicked', () => {
      mockIsOpen = true
      render(<Sidebar />)

      const callsBefore = mockClose.mock.calls.length

      // The backdrop is the div with aria-hidden="true"
      const backdrop = document.querySelector('[aria-hidden="true"]')
      expect(backdrop).toBeTruthy()
      fireEvent.click(backdrop!)

      expect(mockClose.mock.calls.length - callsBefore).toBe(1)
    })

    it('renders duplicate navigation items in mobile sidebar when open', () => {
      mockIsOpen = true
      render(<Sidebar />)

      // Both desktop and mobile sidebars render nav items, so we get duplicates
      const dashboardLinks = screen.getAllByText('Dashboard')
      expect(dashboardLinks.length).toBe(2)
    })
  })
})
