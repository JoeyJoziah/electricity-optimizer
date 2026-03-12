import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataExport } from '@/components/analytics/DataExport'
import '@testing-library/jest-dom'

const mockUseExportRates = jest.fn()
const mockUseExportTypes = jest.fn()

jest.mock('@/lib/hooks/useExport', () => ({
  useExportRates: (...args: unknown[]) => mockUseExportRates(...args),
  useExportTypes: () => mockUseExportTypes(),
}))

describe('DataExport', () => {
  beforeEach(() => {
    mockUseExportRates.mockReset()
    mockUseExportTypes.mockReset()
    mockUseExportTypes.mockReturnValue({
      data: { supported_types: ['electricity', 'natural_gas', 'heating_oil', 'propane'] },
    })
    mockUseExportRates.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    })
  })

  it('renders export form with defaults', () => {
    render(<DataExport state="CT" />)
    expect(screen.getByRole('heading', { name: /Export Data/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Export Data/ })).toBeInTheDocument()
  })

  it('renders utility type selector', () => {
    render(<DataExport state="CT" />)
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThanOrEqual(1)
  })

  it('renders format selector with CSV and JSON options', () => {
    render(<DataExport state="CT" />)
    const selects = screen.getAllByRole('combobox')
    const formatSelect = selects[1]
    expect(formatSelect).toBeInTheDocument()
  })

  it('shows loading state when exporting', () => {
    mockUseExportRates.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    })
    render(<DataExport state="CT" />)
    expect(screen.getByText('Exporting...')).toBeInTheDocument()
  })

  it('shows error state', () => {
    mockUseExportRates.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Export failed'),
    })
    render(<DataExport state="CT" />)
    expect(screen.getByText(/Export failed/)).toBeInTheDocument()
  })

  it('disables button while loading', () => {
    mockUseExportRates.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    })
    render(<DataExport state="CT" />)
    const button = screen.getByText('Exporting...')
    expect(button).toBeDisabled()
  })
})
