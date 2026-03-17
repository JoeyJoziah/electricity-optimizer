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

// Mock next/headers — layout reads the CSP nonce from request headers
jest.mock('next/headers', () => ({
  headers: () => Promise.resolve(new Map([['x-nonce', 'test-nonce']])),
}))

import RootLayout from '@/app/layout'

// Helper to render async server components
async function renderAsync(jsx: Promise<React.JSX.Element>) {
  const resolved = await jsx
  return render(resolved)
}

describe('RootLayout', () => {
  it('renders children inside all providers', async () => {
    await renderAsync(
      RootLayout({
        children: <p data-testid="child-content">Hello</p>,
      })
    )

    // All providers must wrap the children
    expect(screen.getByTestId('query-provider')).toBeInTheDocument()
    expect(screen.getByTestId('auth-provider')).toBeInTheDocument()
    expect(screen.getByTestId('toast-provider')).toBeInTheDocument()
    expect(screen.getByTestId('child-content')).toBeInTheDocument()
  })

  it('wraps providers in correct nesting order', async () => {
    await renderAsync(
      RootLayout({
        children: <span data-testid="child">content</span>,
      })
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

  it('renders children content', async () => {
    await renderAsync(
      RootLayout({
        children: <main>Main content</main>,
      })
    )

    expect(screen.getByText('Main content')).toBeInTheDocument()
  })
})
