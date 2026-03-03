import { render } from '@testing-library/react'
import { axe } from 'jest-axe'
import { LoginForm } from '@/components/auth/LoginForm'
import '@testing-library/jest-dom'

jest.mock('next/link', () => {
  const MockLink = ({
    children,
    href,
    className,
  }: {
    children: React.ReactNode
    href: string
    className?: string
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  )
  MockLink.displayName = 'MockLink'
  return MockLink
})

const mockUseAuth = jest.fn()

jest.mock('@/lib/hooks/useAuth', () => ({
  useAuth: () => mockUseAuth(),
}))

const defaultAuthState = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  clearError: jest.fn(),
  signIn: jest.fn(),
  signUp: jest.fn(),
  signOut: jest.fn(),
  signInWithGoogle: jest.fn(),
  signInWithGitHub: jest.fn(),
  sendMagicLink: jest.fn(),
}

beforeEach(() => {
  mockUseAuth.mockReturnValue(defaultAuthState)
})

describe('LoginForm a11y', () => {
  it('has no accessibility violations in default state', async () => {
    const { container } = render(<LoginForm />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with error displayed', async () => {
    mockUseAuth.mockReturnValue({
      ...defaultAuthState,
      error: 'Invalid email or password',
    })
    const { container } = render(<LoginForm />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations in loading state', async () => {
    mockUseAuth.mockReturnValue({
      ...defaultAuthState,
      isLoading: true,
    })
    const { container } = render(<LoginForm />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('error alert has correct ARIA attributes', () => {
    mockUseAuth.mockReturnValue({
      ...defaultAuthState,
      error: 'Something went wrong',
    })
    const { container } = render(<LoginForm />)
    const alertEl = container.querySelector('[role="alert"]')
    expect(alertEl).toBeInTheDocument()
    expect(alertEl).toHaveAttribute('aria-live', 'polite')
  })

  it('email and password inputs have associated labels', () => {
    const { container } = render(<LoginForm />)
    const emailInput = container.querySelector('#email')
    const passwordInput = container.querySelector('#password')
    const emailLabel = container.querySelector('label[for="email"]')
    const passwordLabel = container.querySelector('label[for="password"]')

    expect(emailInput).toBeInTheDocument()
    expect(passwordInput).toBeInTheDocument()
    expect(emailLabel).toBeInTheDocument()
    expect(passwordLabel).toBeInTheDocument()
  })
})
