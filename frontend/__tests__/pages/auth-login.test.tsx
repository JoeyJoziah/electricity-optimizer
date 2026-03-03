import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import LoginPage from '@/app/(app)/auth/login/page'

// LoginForm has its own comprehensive test suite. Here we test the page wrapper only.
jest.mock('@/components/auth/LoginForm', () => ({
  LoginForm: () => <div data-testid="login-form">LoginForm</div>,
}))

describe('LoginPage', () => {
  beforeEach(() => {
    render(<LoginPage />)
  })

  it('renders the app name heading', () => {
    expect(
      screen.getByRole('heading', { level: 1, name: /electricity optimizer/i })
    ).toBeInTheDocument()
  })

  it('renders the subtitle', () => {
    expect(screen.getByText(/AI-powered electricity price optimization/i)).toBeInTheDocument()
  })

  it('renders the LoginForm component', () => {
    expect(screen.getByTestId('login-form')).toBeInTheDocument()
  })

  it('renders within a centered layout container', () => {
    const container = screen.getByTestId('login-form').closest('div.min-h-screen')
    expect(container).not.toBeNull()
  })
})
