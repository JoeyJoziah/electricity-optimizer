import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock all provider components — we test that they're wired up, not their internals
jest.mock('@/components/providers/QueryProvider', () => ({
  QueryProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="query-provider">{children}</div>
  ),
}))

jest.mock('@/lib/hooks/useAuth', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="auth-provider">{children}</div>
  ),
}))

jest.mock('@/lib/contexts/toast-context', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="toast-provider">{children}</div>
  ),
}))

// Mock next/font/google to avoid network calls
jest.mock('next/font/google', () => ({
  Inter: () => ({ className: 'mock-inter' }),
}))

import RootLayout from '@/app/layout'

describe('RootLayout', () => {
  it('renders children inside all providers', () => {
    render(
      <RootLayout>
        <p data-testid="child-content">Hello</p>
      </RootLayout>
    )

    // All providers must wrap the children
    expect(screen.getByTestId('query-provider')).toBeInTheDocument()
    expect(screen.getByTestId('auth-provider')).toBeInTheDocument()
    expect(screen.getByTestId('toast-provider')).toBeInTheDocument()
    expect(screen.getByTestId('child-content')).toBeInTheDocument()
  })

  it('wraps providers in correct nesting order', () => {
    render(
      <RootLayout>
        <span data-testid="child">content</span>
      </RootLayout>
    )

    const queryProvider = screen.getByTestId('query-provider')
    const authProvider = screen.getByTestId('auth-provider')
    const toastProvider = screen.getByTestId('toast-provider')
    const child = screen.getByTestId('child')

    // QueryProvider is outermost — contains auth
    expect(queryProvider).toContainElement(authProvider)
    // AuthProvider contains toast
    expect(authProvider).toContainElement(toastProvider)
    // ToastProvider contains children
    expect(toastProvider).toContainElement(child)
  })

  it('renders children content', () => {
    render(
      <RootLayout>
        <main>Main content</main>
      </RootLayout>
    )

    expect(screen.getByText('Main content')).toBeInTheDocument()
  })
})
