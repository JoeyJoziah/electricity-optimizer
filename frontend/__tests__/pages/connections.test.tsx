import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import ConnectionsPage from '@/app/(app)/connections/page'

// ConnectionsOverview has its own comprehensive test suite.
// Here we only test the page wrapper: heading, description, layout structure.
jest.mock('@/components/connections/ConnectionsOverview', () => ({
  ConnectionsOverview: () => <div data-testid="connections-overview">ConnectionsOverview</div>,
}))

describe('ConnectionsPage', () => {
  beforeEach(() => {
    render(<ConnectionsPage />)
  })

  it('renders the page heading', () => {
    expect(screen.getByRole('heading', { level: 1, name: /connections/i })).toBeInTheDocument()
  })

  it('renders the page description', () => {
    expect(screen.getByText(/sync your utility rates/i)).toBeInTheDocument()
  })

  it('renders the ConnectionsOverview component', () => {
    expect(screen.getByTestId('connections-overview')).toBeInTheDocument()
  })

  it('constrains content to max-w-4xl', () => {
    const container = screen.getByTestId('connections-overview').closest('div.mx-auto')
    expect(container).not.toBeNull()
    expect(container?.className).toContain('max-w-4xl')
  })
})
