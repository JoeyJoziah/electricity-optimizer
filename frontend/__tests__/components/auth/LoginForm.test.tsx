import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LoginForm } from '@/components/auth/LoginForm'
import '@testing-library/jest-dom'

// Mock useAuth hook
const mockSignIn = jest.fn()
const mockSignInWithGoogle = jest.fn()
const mockSignInWithGitHub = jest.fn()
const mockSendMagicLink = jest.fn()
const mockClearError = jest.fn()

let mockIsLoading = false
let mockError: string | null = null

jest.mock('@/lib/hooks/useAuth', () => ({
  useAuth: () => ({
    signIn: mockSignIn,
    signInWithGoogle: mockSignInWithGoogle,
    signInWithGitHub: mockSignInWithGitHub,
    sendMagicLink: mockSendMagicLink,
    isLoading: mockIsLoading,
    error: mockError,
    clearError: mockClearError,
  }),
}))

// Mock next/link
jest.mock('next/link', () => {
  const MockLink = ({ children, href, ...props }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...props}>{children}</a>
  )
  MockLink.displayName = 'MockLink'
  return MockLink
})

describe('LoginForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockIsLoading = false
    mockError = null
  })

  it('renders the sign in heading', () => {
    render(<LoginForm />)
    expect(screen.getByText('Sign in to your account')).toBeInTheDocument()
  })

  it('renders email and password inputs', () => {
    render(<LoginForm />)
    expect(screen.getByLabelText('Email address')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('hides OAuth buttons when env vars are not set', () => {
    render(<LoginForm />)
    expect(screen.queryByText('Continue with Google')).not.toBeInTheDocument()
    expect(screen.queryByText('Continue with GitHub')).not.toBeInTheDocument()
  })

  it('calls signIn with email and password on form submit', async () => {
    const user = userEvent.setup()
    render(<LoginForm />)

    await user.type(screen.getByLabelText('Email address'), 'test@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in$/i }))

    expect(mockSignIn).toHaveBeenCalledWith('test@example.com', 'password123')
  })

  it('calls onSuccess callback after successful sign in', async () => {
    const onSuccess = jest.fn()
    mockSignIn.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()

    render(<LoginForm onSuccess={onSuccess} />)

    await user.type(screen.getByLabelText('Email address'), 'test@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in$/i }))

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled()
    })
  })

  it('does not call OAuth handlers when buttons are hidden', () => {
    render(<LoginForm />)
    // OAuth buttons are hidden by default (env vars not set)
    expect(screen.queryByText('Continue with Google')).not.toBeInTheDocument()
    expect(screen.queryByText('Continue with GitHub')).not.toBeInTheDocument()
  })

  it('displays error message from auth context', () => {
    mockError = 'Invalid credentials'
    render(<LoginForm />)

    expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
  })

  it('shows loading text during submission', () => {
    mockIsLoading = true
    render(<LoginForm />)

    expect(screen.getByRole('button', { name: /signing in/i })).toBeInTheDocument()
  })

  it('disables submit button while loading', () => {
    mockIsLoading = true
    render(<LoginForm />)

    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled()
  })

  it('switches to magic link mode and hides password field', async () => {
    const user = userEvent.setup()
    render(<LoginForm />)

    await user.click(screen.getByText('Sign in with magic link'))

    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send magic link/i })).toBeInTheDocument()
  })

  it('switches back to password mode from magic link', async () => {
    const user = userEvent.setup()
    render(<LoginForm />)

    await user.click(screen.getByText('Sign in with magic link'))
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()

    await user.click(screen.getByText('Use password instead'))
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('shows magic link sent confirmation after successful send', async () => {
    mockSendMagicLink.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    render(<LoginForm />)

    await user.click(screen.getByText('Sign in with magic link'))
    await user.type(screen.getByLabelText('Email address'), 'test@example.com')
    await user.click(screen.getByRole('button', { name: /send magic link/i }))

    await waitFor(() => {
      expect(screen.getByText('Check your email')).toBeInTheDocument()
    })
    expect(screen.getByText(/test@example.com/)).toBeInTheDocument()
  })

  it('does NOT show success screen when magic link fails', async () => {
    mockSendMagicLink.mockRejectedValueOnce(new Error('Failed to send magic link'))
    const user = userEvent.setup()
    render(<LoginForm />)

    await user.click(screen.getByText('Sign in with magic link'))
    await user.type(screen.getByLabelText('Email address'), 'test@example.com')
    await user.click(screen.getByRole('button', { name: /send magic link/i }))

    await waitFor(() => {
      expect(screen.queryByText('Check your email')).not.toBeInTheDocument()
    })
  })

  it('clears error on form submit', async () => {
    const user = userEvent.setup()
    render(<LoginForm />)

    await user.type(screen.getByLabelText('Email address'), 'test@example.com')
    await user.type(screen.getByLabelText('Password'), 'pass')
    await user.click(screen.getByRole('button', { name: /sign in$/i }))

    expect(mockClearError).toHaveBeenCalled()
  })

  it('renders sign up link', () => {
    render(<LoginForm />)

    const signUpLink = screen.getByRole('link', { name: /sign up/i })
    expect(signUpLink).toBeInTheDocument()
    expect(signUpLink).toHaveAttribute('href', '/auth/signup')
  })
})
