import { render } from '@testing-library/react'
import { axe } from 'jest-axe'
import { LoginForm } from '@/components/auth/LoginForm'
import { SignupForm } from '@/components/auth/SignupForm'
import '@testing-library/jest-dom'

jest.mock('@/lib/hooks/useAuth', () => ({
  useAuth: () => ({
    signIn: jest.fn(),
    signUp: jest.fn(),
    signOut: jest.fn(),
    signInWithGoogle: jest.fn(),
    signInWithGitHub: jest.fn(),
    sendMagicLink: jest.fn(),
    isLoading: false,
    error: null,
    clearError: jest.fn(),
  }),
}))

jest.mock('next/link', () => {
  return ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode
    href: string
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  )
})

describe('LoginForm a11y', () => {
  it('has no accessibility violations in default state', async () => {
    const { container } = render(<LoginForm />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('SignupForm a11y', () => {
  it('has no accessibility violations in default state', async () => {
    const { container } = render(<SignupForm />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
