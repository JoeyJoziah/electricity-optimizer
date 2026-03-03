import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { SignupForm } from '@/components/auth/SignupForm'
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

describe('SignupForm a11y', () => {
  it('has no accessibility violations in default empty state', async () => {
    const { container } = render(<SignupForm />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with auth error displayed', async () => {
    mockUseAuth.mockReturnValue({
      ...defaultAuthState,
      error: 'This email is already in use',
    })
    const { container } = render(<SignupForm />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations in loading state', async () => {
    mockUseAuth.mockReturnValue({
      ...defaultAuthState,
      isLoading: true,
    })
    const { container } = render(<SignupForm />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('confirm password input has aria-invalid when passwords mismatch', async () => {
    const user = userEvent.setup()
    const { container } = render(<SignupForm />)

    const passwordInput = container.querySelector('#password') as HTMLInputElement
    const confirmInput = container.querySelector('#confirmPassword') as HTMLInputElement

    await user.type(passwordInput, 'SecurePass123!')
    await user.type(confirmInput, 'DifferentPass456!')

    expect(confirmInput).toHaveAttribute('aria-invalid', 'true')
    expect(confirmInput).toHaveAttribute('aria-describedby', 'confirmPassword-error')

    const errorEl = container.querySelector('#confirmPassword-error')
    expect(errorEl).toBeInTheDocument()
    expect(errorEl).toHaveAttribute('role', 'alert')
    expect(errorEl).toHaveTextContent('Passwords do not match')
  })

  it('has no accessibility violations when passwords match', async () => {
    const user = userEvent.setup()
    const { container } = render(<SignupForm />)

    const passwordInput = container.querySelector('#password') as HTMLInputElement
    const confirmInput = container.querySelector('#confirmPassword') as HTMLInputElement

    await user.type(passwordInput, 'SecurePass123!')
    await user.type(confirmInput, 'SecurePass123!')

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('top-level error alert has role and aria-live', () => {
    mockUseAuth.mockReturnValue({
      ...defaultAuthState,
      error: 'Network error',
    })
    const { container } = render(<SignupForm />)
    const alertDiv = container.querySelector('div[role="alert"]')
    expect(alertDiv).toBeInTheDocument()
    expect(alertDiv).toHaveAttribute('aria-live', 'polite')
  })
})
