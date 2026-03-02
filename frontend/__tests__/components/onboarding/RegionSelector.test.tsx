import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'

// ---------------------------------------------------------------------------
// Constants mock — provide a small, deterministic subset of regions so tests
// are fast and immune to changes in the full 50-state list.
// ---------------------------------------------------------------------------
jest.mock('@/lib/constants/regions', () => {
  const DEREGULATED_ELECTRICITY_STATES = new Set(['CT', 'TX', 'OH'])

  const US_REGIONS = [
    {
      label: 'Northeast',
      states: [
        { value: 'us_ct', label: 'Connecticut', abbr: 'CT' },
        { value: 'us_ma', label: 'Massachusetts', abbr: 'MA' },
        { value: 'us_vt', label: 'Vermont', abbr: 'VT' },
      ],
    },
    {
      label: 'Southeast',
      states: [
        { value: 'us_fl', label: 'Florida', abbr: 'FL' },
        { value: 'us_ga', label: 'Georgia', abbr: 'GA' },
      ],
    },
    {
      label: 'South Central',
      states: [{ value: 'us_tx', label: 'Texas', abbr: 'TX' }],
    },
  ]

  return { US_REGIONS, DEREGULATED_ELECTRICITY_STATES }
})

jest.mock('@/components/ui/button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    className,
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button onClick={onClick} disabled={disabled} className={className}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant, size }: { children: React.ReactNode; variant?: string; size?: string }) => (
    <span data-testid={`badge-${variant ?? 'default'}`} data-size={size}>
      {children}
    </span>
  ),
}))

jest.mock('lucide-react', () => ({
  MapPin: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-map-pin" {...props} />,
  Search: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-search" {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-zap" {...props} />,
}))

// Import the component after mocks
import { RegionSelector } from '@/components/onboarding/RegionSelector'

describe('RegionSelector', () => {
  const onSelect = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  // --- Render ---

  it('renders the heading', () => {
    render(<RegionSelector onSelect={onSelect} />)

    expect(screen.getByText('Select your state')).toBeInTheDocument()
  })

  it('renders the description text', () => {
    render(<RegionSelector onSelect={onSelect} />)

    expect(
      screen.getByText(/We'll show you local electricity rates/i)
    ).toBeInTheDocument()
  })

  it('renders the MapPin icon', () => {
    render(<RegionSelector onSelect={onSelect} />)

    expect(screen.getByTestId('icon-map-pin')).toBeInTheDocument()
  })

  it('renders the search input', () => {
    render(<RegionSelector onSelect={onSelect} />)

    expect(screen.getByPlaceholderText('Search states...')).toBeInTheDocument()
  })

  it('renders all region group headers', () => {
    render(<RegionSelector onSelect={onSelect} />)

    expect(screen.getByText('Northeast')).toBeInTheDocument()
    expect(screen.getByText('Southeast')).toBeInTheDocument()
    expect(screen.getByText('South Central')).toBeInTheDocument()
  })

  it('renders all states from all groups', () => {
    render(<RegionSelector onSelect={onSelect} />)

    expect(screen.getByText('Connecticut')).toBeInTheDocument()
    expect(screen.getByText('Massachusetts')).toBeInTheDocument()
    expect(screen.getByText('Vermont')).toBeInTheDocument()
    expect(screen.getByText('Florida')).toBeInTheDocument()
    expect(screen.getByText('Georgia')).toBeInTheDocument()
    expect(screen.getByText('Texas')).toBeInTheDocument()
  })

  it('renders state abbreviations', () => {
    render(<RegionSelector onSelect={onSelect} />)

    expect(screen.getByText('(CT)')).toBeInTheDocument()
    expect(screen.getByText('(TX)')).toBeInTheDocument()
  })

  it('renders the Continue button as disabled when nothing selected', () => {
    render(<RegionSelector onSelect={onSelect} />)

    const button = screen.getByRole('button', { name: /continue to dashboard/i })
    expect(button).toBeDisabled()
  })

  it('renders the Continue button with correct label by default', () => {
    render(<RegionSelector onSelect={onSelect} />)

    expect(screen.getByText('Continue to Dashboard')).toBeInTheDocument()
  })

  it('renders disclaimer footnote', () => {
    render(<RegionSelector onSelect={onSelect} />)

    expect(screen.getByText(/deregulated electricity markets/i)).toBeInTheDocument()
  })

  // --- Deregulated badges ---

  it('shows Supplier choice badge for deregulated states', () => {
    render(<RegionSelector onSelect={onSelect} />)

    // CT, TX, OH are deregulated; Florida, Georgia are not
    const supplierChoiceBadges = screen.getAllByText('Supplier choice')
    // Connecticut and Texas should have badges (OH not in our mock data)
    expect(supplierChoiceBadges.length).toBe(2)
  })

  it('does not show Supplier choice badge for regulated states', () => {
    render(<RegionSelector onSelect={onSelect} />)

    const floridaRow = screen.getByText('Florida').closest('button')
    expect(within(floridaRow!).queryByText('Supplier choice')).not.toBeInTheDocument()
  })

  // --- Selection ---

  it('enables the Continue button after selecting a state', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.click(screen.getByText('Connecticut'))

    const button = screen.getByRole('button', { name: /continue to dashboard/i })
    expect(button).not.toBeDisabled()
  })

  it('applies selected styling to the clicked state', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.click(screen.getByText('Connecticut'))

    const stateButton = screen.getByText('Connecticut').closest('button')
    expect(stateButton?.className).toContain('bg-blue-50')
    expect(stateButton?.className).toContain('text-blue-700')
  })

  it('removes selected styling from a previously selected state when another is clicked', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.click(screen.getByText('Connecticut'))
    await user.click(screen.getByText('Texas'))

    const ctButton = screen.getByText('Connecticut').closest('button')
    const txButton = screen.getByText('Texas').closest('button')

    expect(ctButton?.className).not.toContain('bg-blue-50')
    expect(txButton?.className).toContain('bg-blue-50')
  })

  it('calls onSelect with the state value when Continue is clicked', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.click(screen.getByText('Connecticut'))
    await user.click(screen.getByRole('button', { name: /continue to dashboard/i }))

    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith('us_ct')
  })

  it('calls onSelect with correct value for Texas', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.click(screen.getByText('Texas'))
    await user.click(screen.getByRole('button', { name: /continue to dashboard/i }))

    expect(onSelect).toHaveBeenCalledWith('us_tx')
  })

  it('does not call onSelect when Continue is clicked with nothing selected', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    // Button is disabled, so the click should be a no-op
    const button = screen.getByRole('button', { name: /continue to dashboard/i })
    // userEvent respects disabled state
    await user.click(button)

    expect(onSelect).not.toHaveBeenCalled()
  })

  // --- isLoading prop ---

  it('shows "Saving..." text and disables button when isLoading is true', () => {
    render(<RegionSelector onSelect={onSelect} isLoading />)

    const button = screen.getByRole('button', { name: /saving/i })
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('Saving...')
  })

  it('disables the Continue button when isLoading even after selection', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} isLoading />)

    await user.click(screen.getByText('Connecticut'))

    const button = screen.getByRole('button', { name: /saving/i })
    expect(button).toBeDisabled()
  })

  // --- Search / filter ---

  it('filters states as the user types in the search input', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.type(screen.getByPlaceholderText('Search states...'), 'Con')

    expect(screen.getByText('Connecticut')).toBeInTheDocument()
    expect(screen.queryByText('Florida')).not.toBeInTheDocument()
    expect(screen.queryByText('Texas')).not.toBeInTheDocument()
  })

  it('filters by abbreviation', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.type(screen.getByPlaceholderText('Search states...'), 'TX')

    expect(screen.getByText('Texas')).toBeInTheDocument()
    expect(screen.queryByText('Connecticut')).not.toBeInTheDocument()
  })

  it('is case-insensitive in search', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.type(screen.getByPlaceholderText('Search states...'), 'florida')

    expect(screen.getByText('Florida')).toBeInTheDocument()
  })

  it('hides group headers for groups with no matching states', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.type(screen.getByPlaceholderText('Search states...'), 'Con')

    // Only Northeast group should remain
    expect(screen.getByText('Northeast')).toBeInTheDocument()
    expect(screen.queryByText('Southeast')).not.toBeInTheDocument()
    expect(screen.queryByText('South Central')).not.toBeInTheDocument()
  })

  it('shows no-match message when search has no results', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.type(screen.getByPlaceholderText('Search states...'), 'zzzzz')

    expect(screen.getByText(/No states match/i)).toBeInTheDocument()
    expect(screen.getByText(/zzzzz/)).toBeInTheDocument()
  })

  it('restores full list when search is cleared', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    const input = screen.getByPlaceholderText('Search states...')
    await user.type(input, 'Con')
    expect(screen.queryByText('Texas')).not.toBeInTheDocument()

    await user.clear(input)
    expect(screen.getByText('Texas')).toBeInTheDocument()
    expect(screen.getByText('Florida')).toBeInTheDocument()
  })

  it('can select a state that was surfaced by search', async () => {
    const user = userEvent.setup()
    render(<RegionSelector onSelect={onSelect} />)

    await user.type(screen.getByPlaceholderText('Search states...'), 'Texas')
    await user.click(screen.getByText('Texas'))
    await user.click(screen.getByRole('button', { name: /continue to dashboard/i }))

    expect(onSelect).toHaveBeenCalledWith('us_tx')
  })
})
