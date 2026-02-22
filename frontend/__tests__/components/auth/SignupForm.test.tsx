import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SignupForm } from '@/components/auth/SignupForm'
import '@testing-library/jest-dom'

// Mock useAuth hook
const mockSignUp = jest.fn()
const mockSignInWithGoogle = jest.fn()
const mockSignInWithGitHub = jest.fn()
const mockClearError = jest.fn()

let mockIsLoading = false
let mockError: string | null = null

jest.mock('@/lib/hooks/useAuth', () => ({
  useAuth: () => ({
    signUp: mockSignUp,
    signInWithGoogle: mockSignInWithGoogle,
    signInWithGitHub: mockSignInWithGitHub,
    isLoading: mockIsLoading,
    error: mockError,
    clearError: mockClearError,
  }),
}))

// Mock next/link
jest.mock('next/link', () => {
  return ({ children, href, ...props }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...props}>{children}</a>
  )
})

// Helper to fill in a valid form
async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Name (optional)'), 'John Doe')
  await user.type(screen.getByLabelText('Email address'), 'john@example.com')
  await user.type(screen.getByLabelText('Password'), 'StrongPass1!')
  await user.type(screen.getByLabelText('Confirm password'), 'StrongPass1!')
  await user.click(screen.getByLabelText(/I agree to the/i))
}

describe('SignupForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockIsLoading = false
    mockError = null
  })

  it('renders the create account heading', () => {
    render(<SignupForm />)
    expect(screen.getByText('Create your account')).toBeInTheDocument()
  })

  it('renders all form fields', () => {
    render(<SignupForm />)
    expect(screen.getByLabelText('Name (optional)')).toBeInTheDocument()
    expect(screen.getByLabelText('Email address')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirm password')).toBeInTheDocument()
  })

  it('renders terms checkbox with links to Terms and Privacy', () => {
    render(<SignupForm />)

    expect(screen.getByLabelText(/I agree to the/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /terms of service/i })).toHaveAttribute('href', '/terms')
    expect(screen.getByRole('link', { name: /privacy policy/i })).toHaveAttribute('href', '/privacy')
  })

  it('shows password mismatch error when passwords differ', async () => {
    const user = userEvent.setup()
    render(<SignupForm />)

    await user.type(screen.getByLabelText('Password'), 'StrongPass1!')
    await user.type(screen.getByLabelText('Confirm password'), 'DifferentPass1!')

    expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
  })

  it('shows password strength indicator when password is typed', async () => {
    const user = userEvent.setup()
    render(<SignupForm />)

    await user.type(screen.getByLabelText('Password'), 'weak')

    expect(screen.getByText('Weak')).toBeInTheDocument()
  })

  it('shows Medium strength for a moderately complex password', async () => {
    const user = userEvent.setup()
    render(<SignupForm />)

    await user.type(screen.getByLabelText('Password'), 'AbcDef123456')

    expect(screen.getByText('Medium')).toBeInTheDocument()
  })

  it('shows Strong strength for a complex password', async () => {
    const user = userEvent.setup()
    render(<SignupForm />)

    await user.type(screen.getByLabelText('Password'), 'AbcDefgh12345!')

    // 16+ chars, upper, lower, number, special = 6 score = Very Strong
    // 12-15 chars with upper, lower, number, special = 5 score = Strong
    expect(screen.getByText(/strong/i)).toBeInTheDocument()
  })

  it('displays password requirement checklist', async () => {
    const user = userEvent.setup()
    render(<SignupForm />)

    await user.type(screen.getByLabelText('Password'), 'a')

    expect(screen.getByText('At least 12 characters')).toBeInTheDocument()
    expect(screen.getByText('One uppercase letter')).toBeInTheDocument()
    expect(screen.getByText('One lowercase letter')).toBeInTheDocument()
    expect(screen.getByText('One number')).toBeInTheDocument()
    expect(screen.getByText('One special character')).toBeInTheDocument()
  })

  it('shows validation error when terms not accepted', async () => {
    const user = userEvent.setup()
    render(<SignupForm />)

    await user.type(screen.getByLabelText('Email address'), 'john@example.com')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1!StrongPass1!')
    await user.type(screen.getByLabelText('Confirm password'), 'StrongPass1!StrongPass1!')
    // Do NOT click terms checkbox

    // The submit button should be disabled when terms not accepted
    const submitButton = screen.getByRole('button', { name: /create account/i })
    expect(submitButton).toBeDisabled()
  })

  it('calls signUp with correct data on valid submission', async () => {
    mockSignUp.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    render(<SignupForm />)

    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => {
      expect(mockSignUp).toHaveBeenCalledWith('john@example.com', 'StrongPass1!', 'John Doe')
    })
  })

  it('calls onSuccess after successful signup', async () => {
    mockSignUp.mockResolvedValueOnce(undefined)
    const onSuccess = jest.fn()
    const user = userEvent.setup()

    render(<SignupForm onSuccess={onSuccess} />)

    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled()
    })
  })

  it('displays error from auth context', () => {
    mockError = 'Email already exists'
    render(<SignupForm />)

    expect(screen.getByText('Email already exists')).toBeInTheDocument()
  })

  it('shows loading state during submission', () => {
    mockIsLoading = true
    render(<SignupForm />)

    expect(screen.getByRole('button', { name: /creating account/i })).toBeInTheDocument()
  })

  it('disables submit button when password requirements not met', async () => {
    const user = userEvent.setup()
    render(<SignupForm />)

    await user.type(screen.getByLabelText('Email address'), 'john@example.com')
    await user.type(screen.getByLabelText('Password'), 'weak')
    await user.type(screen.getByLabelText('Confirm password'), 'weak')
    await user.click(screen.getByLabelText(/I agree to the/i))

    const submitButton = screen.getByRole('button', { name: /create account/i })
    expect(submitButton).toBeDisabled()
  })

  it('renders OAuth buttons for Google and GitHub', () => {
    render(<SignupForm />)
    expect(screen.getByText('Continue with Google')).toBeInTheDocument()
    expect(screen.getByText('Continue with GitHub')).toBeInTheDocument()
  })

  it('calls signInWithGoogle when Google button clicked', async () => {
    const user = userEvent.setup()
    render(<SignupForm />)

    await user.click(screen.getByText('Continue with Google'))

    expect(mockSignInWithGoogle).toHaveBeenCalled()
  })

  it('renders sign in link', () => {
    render(<SignupForm />)

    const signInLink = screen.getByRole('link', { name: /sign in/i })
    expect(signInLink).toBeInTheDocument()
    expect(signInLink).toHaveAttribute('href', '/auth/login')
  })
})
