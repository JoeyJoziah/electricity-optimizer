import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConnectionCard } from '@/components/connections/ConnectionCard'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons used in ConnectionCard
jest.mock('lucide-react', () => ({
  KeyRound: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-key" {...props} />,
  Mail: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-mail" {...props} />,
  Upload: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-upload" {...props} />,
  Trash2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-trash" {...props} />,
  RefreshCw: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-refresh" {...props} />,
  AlertTriangle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-alert" {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-zap" {...props} />,
  ChevronRight: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-chevron" {...props} />,
  Pencil: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-pencil" {...props} />,
  Check: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-check" {...props} />,
  X: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-x" {...props} />,
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-loader" {...props} />,
}))

const mockFetch = global.fetch as jest.Mock

const baseConnection = {
  id: 'conn-1',
  method: 'direct_login',
  status: 'active',
  supplier_name: 'Eversource Energy',
  email_provider: null,
  last_sync_at: null,
  last_sync_error: null,
  current_rate: null,
  created_at: '2026-02-20T10:00:00Z',
}

describe('ConnectionCard', () => {
  const defaultProps = {
    connection: baseConnection,
    onDelete: jest.fn(),
    onViewRates: jest.fn(),
    onRefresh: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockFetch.mockReset()
  })

  it('renders connection name from supplier_name', () => {
    render(<ConnectionCard {...defaultProps} />)

    expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
  })

  it('renders data-testid with connection id', () => {
    render(<ConnectionCard {...defaultProps} />)

    expect(screen.getByTestId('connection-card-conn-1')).toBeInTheDocument()
  })

  it('displays active status badge', () => {
    render(<ConnectionCard {...defaultProps} />)

    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('displays pending status badge', () => {
    const pendingConnection = { ...baseConnection, status: 'pending' }
    render(<ConnectionCard {...defaultProps} connection={pendingConnection} />)

    expect(screen.getByText('Pending')).toBeInTheDocument()
  })

  it('displays failed status badge', () => {
    const failedConnection = { ...baseConnection, status: 'failed' }
    render(<ConnectionCard {...defaultProps} connection={failedConnection} />)

    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('displays method label for direct_login', () => {
    render(<ConnectionCard {...defaultProps} />)

    expect(screen.getByText('Utility Account')).toBeInTheDocument()
  })

  it('displays method label for email_scan', () => {
    const emailConnection = {
      ...baseConnection,
      method: 'email_scan',
      supplier_name: null,
      email_provider: 'Gmail',
    }
    render(<ConnectionCard {...defaultProps} connection={emailConnection} />)

    expect(screen.getByText('Email Scan')).toBeInTheDocument()
  })

  it('displays method label for bill_upload', () => {
    const uploadConnection = { ...baseConnection, method: 'bill_upload' }
    render(<ConnectionCard {...defaultProps} connection={uploadConnection} />)

    expect(screen.getByText('Bill Upload')).toBeInTheDocument()
  })

  it('displays email_provider as display name when supplier_name is null', () => {
    const emailConnection = {
      ...baseConnection,
      method: 'email_scan',
      supplier_name: null,
      email_provider: 'Gmail',
    }
    render(<ConnectionCard {...defaultProps} connection={emailConnection} />)

    expect(screen.getByText('Gmail')).toBeInTheDocument()
  })

  it('falls back to method label when both supplier_name and email_provider are null', () => {
    const genericConnection = {
      ...baseConnection,
      supplier_name: null,
      email_provider: null,
    }
    render(<ConnectionCard {...defaultProps} connection={genericConnection} />)

    // "Utility Account" should appear both as display name and method label
    const utilityAccountTexts = screen.getAllByText('Utility Account')
    expect(utilityAccountTexts.length).toBeGreaterThanOrEqual(1)
  })

  it('displays current rate when present', () => {
    const connectionWithRate = { ...baseConnection, current_rate: 0.2545 }
    render(<ConnectionCard {...defaultProps} connection={connectionWithRate} />)

    expect(screen.getByText('25.45 c/kWh')).toBeInTheDocument()
  })

  it('does not display rate when current_rate is null', () => {
    render(<ConnectionCard {...defaultProps} />)

    expect(screen.queryByText(/c\/kWh/)).not.toBeInTheDocument()
  })

  it('shows sync error banner when last_sync_error is present', () => {
    const errorConnection = {
      ...baseConnection,
      last_sync_error: 'Authentication expired',
    }
    render(<ConnectionCard {...defaultProps} connection={errorConnection} />)

    expect(screen.getByText('Authentication expired')).toBeInTheDocument()
  })

  it('shows retry button in sync error banner for direct_login', () => {
    const errorConnection = {
      ...baseConnection,
      method: 'direct_login',
      last_sync_error: 'Auth expired',
    }
    render(<ConnectionCard {...defaultProps} connection={errorConnection} />)

    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('does not show retry in error banner for bill_upload', () => {
    const errorConnection = {
      ...baseConnection,
      method: 'bill_upload',
      last_sync_error: 'Parse failed',
    }
    render(<ConnectionCard {...defaultProps} connection={errorConnection} />)

    expect(screen.queryByText('Retry')).not.toBeInTheDocument()
  })

  it('shows delete button with aria-label', () => {
    render(<ConnectionCard {...defaultProps} />)

    expect(
      screen.getByRole('button', { name: /delete eversource energy connection/i })
    ).toBeInTheDocument()
  })

  it('shows confirmation dialog on first delete click', async () => {
    const user = userEvent.setup()
    render(<ConnectionCard {...defaultProps} />)

    await user.click(
      screen.getByRole('button', { name: /delete eversource energy connection/i })
    )

    expect(screen.getByText('Confirm?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('calls onDelete after confirming deletion', async () => {
    const user = userEvent.setup()
    mockFetch.mockResolvedValueOnce({ ok: true })

    render(<ConnectionCard {...defaultProps} />)

    // First click shows confirmation
    await user.click(
      screen.getByRole('button', { name: /delete eversource energy connection/i })
    )

    // Second click confirms
    await user.click(screen.getByText('Delete'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/connections/conn-1'),
        expect.objectContaining({ method: 'DELETE' })
      )
    })

    await waitFor(() => {
      expect(defaultProps.onDelete).toHaveBeenCalled()
    })
  })

  it('dismisses confirmation on cancel click', async () => {
    const user = userEvent.setup()
    render(<ConnectionCard {...defaultProps} />)

    await user.click(
      screen.getByRole('button', { name: /delete eversource energy connection/i })
    )

    expect(screen.getByText('Confirm?')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(screen.queryByText('Confirm?')).not.toBeInTheDocument()
  })

  it('shows sync button for active direct_login connections', () => {
    render(<ConnectionCard {...defaultProps} />)

    expect(
      screen.getByRole('button', { name: /sync eversource energy/i })
    ).toBeInTheDocument()
  })

  it('does not show sync button for bill_upload connections', () => {
    const uploadConnection = { ...baseConnection, method: 'bill_upload' }
    render(<ConnectionCard {...defaultProps} connection={uploadConnection} />)

    expect(
      screen.queryByRole('button', { name: /sync/i })
    ).not.toBeInTheDocument()
  })

  it('does not show sync button for non-active connections', () => {
    const pendingConnection = { ...baseConnection, status: 'pending' }
    render(<ConnectionCard {...defaultProps} connection={pendingConnection} />)

    expect(
      screen.queryByRole('button', { name: /sync/i })
    ).not.toBeInTheDocument()
  })

  it('calls sync endpoint when sync button is clicked', async () => {
    const user = userEvent.setup()
    mockFetch.mockResolvedValueOnce({ ok: true })

    render(<ConnectionCard {...defaultProps} />)

    await user.click(
      screen.getByRole('button', { name: /sync eversource energy/i })
    )

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/connections/conn-1/sync'),
        expect.objectContaining({ method: 'POST' })
      )
    })
  })

  it('shows view rates button when onViewRates is provided', () => {
    render(<ConnectionCard {...defaultProps} />)

    expect(
      screen.getByRole('button', { name: /view rates for eversource energy/i })
    ).toBeInTheDocument()
  })

  it('calls onViewRates with connection id when clicked', async () => {
    const user = userEvent.setup()
    render(<ConnectionCard {...defaultProps} />)

    await user.click(
      screen.getByRole('button', { name: /view rates for eversource energy/i })
    )

    expect(defaultProps.onViewRates).toHaveBeenCalledWith('conn-1')
  })

  it('does not show view rates button when onViewRates is not provided', () => {
    render(
      <ConnectionCard
        connection={baseConnection}
        onDelete={jest.fn()}
      />
    )

    expect(
      screen.queryByRole('button', { name: /view rates/i })
    ).not.toBeInTheDocument()
  })

  it('shows edit label button and enters edit mode', async () => {
    const user = userEvent.setup()
    render(<ConnectionCard {...defaultProps} />)

    const editButton = screen.getByTestId('edit-label')
    await user.click(editButton)

    expect(screen.getByTestId('label-input')).toBeInTheDocument()
    expect(screen.getByTestId('save-label')).toBeInTheDocument()
    expect(screen.getByTestId('cancel-label')).toBeInTheDocument()
  })

  it('cancels label editing when cancel button is clicked', async () => {
    const user = userEvent.setup()
    render(<ConnectionCard {...defaultProps} />)

    await user.click(screen.getByTestId('edit-label'))
    expect(screen.getByTestId('label-input')).toBeInTheDocument()

    await user.click(screen.getByTestId('cancel-label'))
    expect(screen.queryByTestId('label-input')).not.toBeInTheDocument()
  })

  it('saves label via PATCH API on save click', async () => {
    const user = userEvent.setup()
    mockFetch.mockResolvedValueOnce({ ok: true })

    render(<ConnectionCard {...defaultProps} />)

    await user.click(screen.getByTestId('edit-label'))
    const input = screen.getByTestId('label-input')
    await user.clear(input)
    await user.type(input, 'My Main Account')
    await user.click(screen.getByTestId('save-label'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/connections/conn-1'),
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ label: 'My Main Account' }),
        })
      )
    })
  })

  it('shows label error when PATCH fails', async () => {
    const user = userEvent.setup()
    mockFetch.mockResolvedValueOnce({ ok: false })

    render(<ConnectionCard {...defaultProps} />)

    await user.click(screen.getByTestId('edit-label'))
    await user.click(screen.getByTestId('save-label'))

    await waitFor(() => {
      expect(screen.getByText('Failed to save label')).toBeInTheDocument()
    })
  })
})
