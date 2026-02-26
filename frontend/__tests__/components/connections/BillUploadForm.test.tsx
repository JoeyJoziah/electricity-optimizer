import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BillUploadForm } from '@/components/connections/BillUploadForm'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  Upload: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-upload" {...props} />,
  FileText: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-filetext" {...props} />,
  X: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-x" {...props} />,
  AlertCircle: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-alert" {...props} />,
  CheckCircle2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-check" {...props} />,
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-loader" {...props} />,
  RotateCcw: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-rotate" {...props} />,
  Image: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-image" {...props} />,
  File: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-file" {...props} />,
  Zap: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-zap" {...props} />,
  Calendar: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-calendar" {...props} />,
  DollarSign: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-dollar" {...props} />,
  Gauge: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-gauge" {...props} />,
}))

const mockFetch = global.fetch as jest.Mock

describe('BillUploadForm', () => {
  const defaultProps = {
    connectionId: 'conn-1',
    onUploadComplete: jest.fn(),
    onComplete: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockFetch.mockReset()
  })

  it('renders the upload form heading', () => {
    render(<BillUploadForm {...defaultProps} />)

    expect(screen.getByText('Upload Utility Bill')).toBeInTheDocument()
    expect(
      screen.getByText(/upload your bill and we will extract rate data/i)
    ).toBeInTheDocument()
  })

  it('renders the drag and drop area', () => {
    render(<BillUploadForm {...defaultProps} />)

    expect(
      screen.getByText('Drag and drop your bill here')
    ).toBeInTheDocument()
    expect(screen.getByText('or click to browse files')).toBeInTheDocument()
  })

  it('renders accepted file type badges', () => {
    render(<BillUploadForm {...defaultProps} />)

    expect(screen.getByText('PDF')).toBeInTheDocument()
    expect(screen.getByText('PNG')).toBeInTheDocument()
    expect(screen.getByText('JPG')).toBeInTheDocument()
  })

  it('displays max file size text', () => {
    render(<BillUploadForm {...defaultProps} />)

    expect(screen.getByText('Max file size: 10 MB')).toBeInTheDocument()
  })

  it('has a hidden file input with correct accept attribute', () => {
    render(<BillUploadForm {...defaultProps} />)

    const fileInput = document.querySelector('input[type="file"]')
    expect(fileInput).toBeInTheDocument()
    expect(fileInput).toHaveAttribute('accept', '.pdf,.png,.jpg,.jpeg')
  })

  it('upload button is disabled when no file is selected', () => {
    render(<BillUploadForm {...defaultProps} />)

    const uploadButton = screen.getByRole('button', { name: /upload bill/i })
    expect(uploadButton).toBeDisabled()
  })

  it('shows selected file name after choosing a file', async () => {
    render(<BillUploadForm {...defaultProps} />)

    const file = new File(['test content'], 'bill.pdf', {
      type: 'application/pdf',
    })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(screen.getByText('bill.pdf')).toBeInTheDocument()
  })

  it('enables upload button after selecting a valid file', async () => {
    render(<BillUploadForm {...defaultProps} />)

    const file = new File(['test content'], 'bill.pdf', {
      type: 'application/pdf',
    })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    const uploadButton = screen.getByRole('button', { name: /upload bill/i })
    expect(uploadButton).not.toBeDisabled()
  })

  it('shows error for unsupported file type', () => {
    render(<BillUploadForm {...defaultProps} />)

    const file = new File(['test'], 'data.csv', { type: 'text/csv' })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(
      screen.getByText(
        'Unsupported file type. Please upload a PDF, PNG, or JPG file.'
      )
    ).toBeInTheDocument()
  })

  it('shows error when file exceeds maximum size', () => {
    render(<BillUploadForm {...defaultProps} />)

    // Create a file > 10 MB
    const largeContent = new ArrayBuffer(11 * 1024 * 1024)
    const file = new File([largeContent], 'huge.pdf', {
      type: 'application/pdf',
    })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(screen.getByText(/file is too large/i)).toBeInTheDocument()
  })

  it('shows remove file button when a file is selected', () => {
    render(<BillUploadForm {...defaultProps} />)

    const file = new File(['test'], 'bill.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(
      screen.getByRole('button', { name: /remove selected file/i })
    ).toBeInTheDocument()
  })

  it('clears file when remove button is clicked', async () => {
    const user = userEvent.setup()
    render(<BillUploadForm {...defaultProps} />)

    const file = new File(['test'], 'bill.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getByText('bill.pdf')).toBeInTheDocument()

    await user.click(
      screen.getByRole('button', { name: /remove selected file/i })
    )

    expect(screen.queryByText('bill.pdf')).not.toBeInTheDocument()
  })

  it('has an accessible drop zone with role="button"', () => {
    render(<BillUploadForm {...defaultProps} />)

    const dropZone = screen.getByRole('button', { name: /upload a bill file/i })
    expect(dropZone).toBeInTheDocument()
    expect(dropZone).toHaveAttribute('tabindex', '0')
  })

  it('accepts PDF files via file input', () => {
    render(<BillUploadForm {...defaultProps} />)

    const file = new File(['pdf content'], 'test.pdf', {
      type: 'application/pdf',
    })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(screen.getByText('test.pdf')).toBeInTheDocument()
    expect(
      screen.queryByText(/unsupported file type/i)
    ).not.toBeInTheDocument()
  })

  it('accepts PNG files via file input', () => {
    render(<BillUploadForm {...defaultProps} />)

    const file = new File(['png content'], 'bill.png', {
      type: 'image/png',
    })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(screen.getByText('bill.png')).toBeInTheDocument()
    expect(
      screen.queryByText(/unsupported file type/i)
    ).not.toBeInTheDocument()
  })

  it('accepts JPEG files via file input', () => {
    render(<BillUploadForm {...defaultProps} />)

    const file = new File(['jpeg content'], 'scan.jpg', {
      type: 'image/jpeg',
    })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(screen.getByText('scan.jpg')).toBeInTheDocument()
    expect(
      screen.queryByText(/unsupported file type/i)
    ).not.toBeInTheDocument()
  })

  it('displays file size for selected file', () => {
    render(<BillUploadForm {...defaultProps} />)

    const content = 'a'.repeat(2048) // ~2 KB
    const file = new File([content], 'bill.pdf', {
      type: 'application/pdf',
    })
    const fileInput = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(screen.getByText(/2\.0 KB/)).toBeInTheDocument()
  })
})
