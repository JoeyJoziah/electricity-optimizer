import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConnectionUploadFlow } from '@/components/connections/ConnectionUploadFlow'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons (needs all icons used across sub-components)
jest.mock('lucide-react', () => ({
  Upload: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-upload" {...props} />,
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-loader" {...props} />,
  AlertCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-alert" {...props} />,
  CheckCircle2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-check" {...props} />,
  ArrowLeft: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-back" {...props} />,
  FileText: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-filetext" {...props} />,
  X: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-x" {...props} />,
  RotateCcw: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-rotate" {...props} />,
  Image: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-image" {...props} />,
  File: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-file" {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-zap" {...props} />,
  Calendar: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-calendar" {...props} />,
  DollarSign: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-dollar" {...props} />,
  Gauge: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-gauge" {...props} />,
  TrendingUp: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-trending" {...props} />,
  RefreshCw: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-refresh" {...props} />,
}))

const mockFetch = global.fetch as jest.Mock

describe('ConnectionUploadFlow', () => {
  const defaultProps = {
    onComplete: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockFetch.mockReset()
  })

  it('shows loading state while creating connection', () => {
    // Never resolve so loading persists
    mockFetch.mockImplementation(() => new Promise(() => {}))
    render(<ConnectionUploadFlow {...defaultProps} />)

    expect(screen.getByText('Setting up bill upload...')).toBeInTheDocument()
  })

  it('shows error state when connection creation fails', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: 'Server error' }),
    })

    render(<ConnectionUploadFlow {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument()
    })

    expect(screen.getByText('Try Again')).toBeInTheDocument()
    expect(screen.getByText('Back to Connections')).toBeInTheDocument()
  })

  it('shows upgrade gate on 403 error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'Forbidden' }),
    })

    render(<ConnectionUploadFlow {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Upgrade Required')).toBeInTheDocument()
    })

    expect(
      screen.getByText(/bill upload is available on pro and business plans/i)
    ).toBeInTheDocument()
    expect(screen.getByText('View Plans')).toBeInTheDocument()
  })

  it('transitions to upload step after connection created', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({ id: 'conn-upload-1', supplier_name: null }),
    })

    render(<ConnectionUploadFlow {...defaultProps} />)

    await waitFor(() => {
      expect(
        screen.getByText('Upload your utility bill')
      ).toBeInTheDocument()
    })

    // BillUploadForm should be rendered
    expect(screen.getByText('Upload Utility Bill')).toBeInTheDocument()
  })

  it('calls onComplete when Back to Connections is clicked on error', async () => {
    const user = userEvent.setup()
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: 'Error' }),
    })

    render(<ConnectionUploadFlow {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Back to Connections')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Back to Connections'))
    expect(defaultProps.onComplete).toHaveBeenCalled()
  })

  it('retries connection creation when Try Again is clicked', async () => {
    const user = userEvent.setup()

    // First call fails, second succeeds
    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: 'Error' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({ id: 'conn-upload-1', supplier_name: null }),
      })

    render(<ConnectionUploadFlow {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Try Again')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Try Again'))

    await waitFor(() => {
      expect(screen.getByText('Upload Utility Bill')).toBeInTheDocument()
    })
  })

  it('renders step indicators during upload step', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({ id: 'conn-upload-1', supplier_name: null }),
    })

    render(<ConnectionUploadFlow {...defaultProps} />)

    await waitFor(() => {
      expect(
        screen.getByText('Upload your utility bill')
      ).toBeInTheDocument()
    })

    // Step indicator should show step 2 of 3
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('shows network error on connection creation failure', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network failure'))

    render(<ConnectionUploadFlow {...defaultProps} />)

    await waitFor(() => {
      expect(
        screen.getByText(/network error. please check your connection/i)
      ).toBeInTheDocument()
    })
  })
})
