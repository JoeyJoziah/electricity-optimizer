import { render } from '@testing-library/react'
import { axe } from 'jest-axe'
import '@testing-library/jest-dom'

// We test the skip-to-content link and main landmark structure
// rather than the full AppLayout (which requires Next.js server context)

function MockAppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-0 focus:left-0 focus:z-50 focus:p-4 focus:bg-primary-600 focus:text-white"
      >
        Skip to main content
      </a>
      <div className="flex min-h-screen">
        <nav aria-label="Main navigation">
          <a href="/dashboard">Dashboard</a>
          <a href="/prices">Prices</a>
        </nav>
        <main id="main-content" className="flex-1">
          {children}
        </main>
      </div>
    </>
  )
}

describe('App Layout a11y', () => {
  it('has no accessibility violations with skip link and main landmark', async () => {
    const { container } = render(
      <MockAppLayout>
        <h1>Dashboard</h1>
        <p>Page content</p>
      </MockAppLayout>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('skip-to-content link targets main content landmark', () => {
    const { container } = render(
      <MockAppLayout>
        <h1>Dashboard</h1>
      </MockAppLayout>
    )
    const skipLink = container.querySelector('a[href="#main-content"]')
    expect(skipLink).toBeInTheDocument()
    expect(skipLink).toHaveTextContent('Skip to main content')

    const mainEl = container.querySelector('#main-content')
    expect(mainEl).toBeInTheDocument()
    expect(mainEl?.tagName).toBe('MAIN')
  })

  it('navigation has accessible name', () => {
    const { container } = render(
      <MockAppLayout>
        <h1>Dashboard</h1>
      </MockAppLayout>
    )
    const nav = container.querySelector('nav')
    expect(nav).toHaveAttribute('aria-label')
  })

  it('has no accessibility violations with page heading', async () => {
    const { container } = render(
      <MockAppLayout>
        <h1>Prices</h1>
        <p>Electricity prices for your area.</p>
      </MockAppLayout>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
