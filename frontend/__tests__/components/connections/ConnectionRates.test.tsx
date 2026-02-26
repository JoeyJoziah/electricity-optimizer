import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConnectionRates } from '@/components/connections/ConnectionRates'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons (includes Loader2 needed by Button component)
jest.mock('lucide-react', () => ({
  TrendingUp: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-trending" {...props} />,
  Calendar: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-calendar" {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-zap" {...props} />,
  Upload: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-upload" {...props} />,
  ArrowLeft: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-back" {...props} />,
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-loader" {...props} />,
  AlertCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-alert" {...props} />,
  RefreshCw: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-refresh" {...props} />,
}))

const mockFetch = global.fetch as jest.Mock

const mockRates = [
  {
    id: 'rate-1',
    rate_per_kwh: 0.2545,
    currency: 'USD',
    period_start: '2026-02-01',
    period_end: '2026-02-28',
    usage_kwh: 850,
    amount: 216.33,
    source: 'direct_sync',
    extracted_at: '2026-02-20T10:00:00Z',
  },
  {
    id: 'rate-2',
    rate_per_kwh: 0.2312,
    currency: 'USD',
    period_start: '2026-01-01',
    period_end: '2026-01-31',
    usage_kwh: 920,
    amount: 212.70,
    source: 'bill_upload',
    extracted_at: '2026-02-10T10:00:00Z',
  },
  {
    id: 'rate-3',
    rate_per_kwh: 0.2100,
    currency: 'USD',
    period_start: '2025-12-01',
    period_end: '2025-12-31',
    usage_kwh: null,
    amount: null,
    source: 'direct_sync',
    extracted_at: '2026-01-05T10:00:00Z',
  },
]

describe('ConnectionRates', () => {
  const defaultProps = {
    connectionId: 'conn-1',
    connectionMethod: 'direct_login',
    supplierName: 'Eversource Energy',
    onBack: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockFetch.mockReset()
  })

  it('shows loading state while fetching rates', () => {
    mockFetch.mockImplementation(() => new Promise(() => {}))
    render(<ConnectionRates {...defaultProps} />)

    expect(screen.getByText('Loading rates...')).toBeInTheDocument()
  })

  it('renders heading with supplier name', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(
        screen.getByText('Eversource Energy Rates')
      ).toBeInTheDocument()
    })
  })

  it('renders fallback heading when supplier name is null', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} supplierName={null} />)

    await waitFor(() => {
      expect(screen.getByText('Connection Rates')).toBeInTheDocument()
    })
  })

  it('displays rate count', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('3 rates extracted')).toBeInTheDocument()
    })
  })

  it('displays current rate highlight for most recent rate', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Current Rate')).toBeInTheDocument()
    })

    // Rate appears in both the highlight card and the table row
    const rateElements = screen.getAllByText('25.45 c/kWh')
    expect(rateElements.length).toBeGreaterThanOrEqual(2)
  })

  it('displays usage and amount for current rate', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Current Rate')).toBeInTheDocument()
    })

    // Usage appears in both the highlight card and the table, use getAllByText
    const usageElements = screen.getAllByText('850 kWh')
    expect(usageElements.length).toBeGreaterThanOrEqual(1)

    // Amount formatted as currency appears in both places
    const amountElements = screen.getAllByText('$216.33')
    expect(amountElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders rate table with headers and source badges', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Current Rate')).toBeInTheDocument()
    })

    // Table headers
    expect(screen.getByText('Period')).toBeInTheDocument()
    expect(screen.getByText('Rate')).toBeInTheDocument()
    expect(screen.getByText('Source')).toBeInTheDocument()

    // Source badges
    expect(screen.getAllByText('Sync')).toHaveLength(2)
    expect(screen.getByText('Upload')).toBeInTheDocument()

    // Latest badge on first row
    expect(screen.getByText('Latest')).toBeInTheDocument()
  })

  it('shows em dash for null usage and amount values', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Current Rate')).toBeInTheDocument()
    })

    // Rate 3 has null usage and amount, should show em dash
    const emDashes = screen.getAllByText('\u2014')
    expect(emDashes.length).toBeGreaterThanOrEqual(2)
  })

  it('shows empty state when no rates', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: [] }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('No Rates Yet')).toBeInTheDocument()
    })

    expect(
      screen.getByText(
        /rate data will appear here after a successful sync/i
      )
    ).toBeInTheDocument()
  })

  it('shows upload-specific empty state for bill_upload method', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: [] }),
    })

    const onUploadAnother = jest.fn()

    render(
      <ConnectionRates
        {...defaultProps}
        connectionMethod="bill_upload"
        onUploadAnother={onUploadAnother}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('No Rates Yet')).toBeInTheDocument()
    })

    expect(
      screen.getByText('Upload a bill to extract rate data.')
    ).toBeInTheDocument()

    expect(
      screen.getByRole('button', { name: /upload a bill/i })
    ).toBeInTheDocument()
  })

  it('shows error state on fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Failed to load rates')).toBeInTheDocument()
    })

    expect(screen.getByText('Try again')).toBeInTheDocument()
  })

  it('shows upgrade gate on 403 error', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 403 })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Upgrade Required')).toBeInTheDocument()
    })

    expect(
      screen.getByText(
        /rate history is available on pro and business plans/i
      )
    ).toBeInTheDocument()
  })

  it('calls onBack when back button is clicked', async () => {
    const user = userEvent.setup()
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Current Rate')).toBeInTheDocument()
    })

    const backButton = screen.getByRole('button', {
      name: /back to connections/i,
    })
    await user.click(backButton)

    expect(defaultProps.onBack).toHaveBeenCalled()
  })

  it('shows refresh button that refetches rates', async () => {
    const user = userEvent.setup()
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ rates: mockRates }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ rates: mockRates }),
      })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Current Rate')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Refresh'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2)
    })
  })

  it('shows upload another bill button for bill_upload method', async () => {
    const onUploadAnother = jest.fn()
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(
      <ConnectionRates
        {...defaultProps}
        connectionMethod="bill_upload"
        onUploadAnother={onUploadAnother}
      />
    )

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /upload another bill/i })
      ).toBeInTheDocument()
    })
  })

  it('does not show upload another button for direct_login method', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Current Rate')).toBeInTheDocument()
    })

    expect(
      screen.queryByRole('button', { name: /upload another bill/i })
    ).not.toBeInTheDocument()
  })

  it('formats all rates correctly as cents per kWh', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: mockRates }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Current Rate')).toBeInTheDocument()
    })

    // All three rates should appear (first in highlight + table, others just in table)
    const rate1Elements = screen.getAllByText('25.45 c/kWh')
    expect(rate1Elements.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('23.12 c/kWh')).toBeInTheDocument()
    expect(screen.getByText('21.00 c/kWh')).toBeInTheDocument()
  })

  it('displays singular "rate" for single rate count', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rates: [mockRates[0]] }),
    })

    render(<ConnectionRates {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('1 rate extracted')).toBeInTheDocument()
    })
  })
})
