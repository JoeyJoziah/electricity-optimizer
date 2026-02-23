import { render, screen } from '@testing-library/react'
import { Sidebar } from '@/components/layout/Sidebar'
import '@testing-library/jest-dom'

// Track the mock pathname for changing it between tests
let mockPathname = '/dashboard'

// Mock next/navigation
jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}))

// Mock next/link
jest.mock('next/link', () => {
  return ({ children, href, className, ...props }: { children: React.ReactNode; href: string; className?: string }) => (
    <a href={href} className={className} {...props}>{children}</a>
  )
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

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  LayoutDashboard: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-dashboard" {...props} />,
  TrendingUp: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-prices" {...props} />,
  Building2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-suppliers" {...props} />,
  Calendar: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-optimize" {...props} />,
  Settings: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-settings" {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-zap" {...props} />,
  LogOut: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-logout" {...props} />,
  User: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-user" {...props} />,
}))

describe('Sidebar', () => {
  beforeEach(() => {
    mockPathname = '/dashboard'
  })

  it('renders the brand name', () => {
    render(<Sidebar />)

    expect(screen.getByText('Electricity Optimizer')).toBeInTheDocument()
  })

  it('renders the Zap logo icon', () => {
    render(<Sidebar />)

    expect(screen.getByTestId('icon-zap')).toBeInTheDocument()
  })

  it('renders all 5 navigation items', () => {
    render(<Sidebar />)

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Prices')).toBeInTheDocument()
    expect(screen.getByText('Suppliers')).toBeInTheDocument()
    expect(screen.getByText('Optimize')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('renders navigation links with correct hrefs', () => {
    render(<Sidebar />)

    expect(screen.getByText('Dashboard').closest('a')).toHaveAttribute('href', '/dashboard')
    expect(screen.getByText('Prices').closest('a')).toHaveAttribute('href', '/prices')
    expect(screen.getByText('Suppliers').closest('a')).toHaveAttribute('href', '/suppliers')
    expect(screen.getByText('Optimize').closest('a')).toHaveAttribute('href', '/optimize')
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
})
