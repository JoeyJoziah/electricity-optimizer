import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'

// --- Store mock ---
const mockSetRegion = jest.fn()
const mockSetUtilityTypes = jest.fn()
const mockSetCurrentSupplierStore = jest.fn()
const mockSetAnnualUsage = jest.fn()
const mockSetPeakDemand = jest.fn()
const mockSetNotificationPreferences = jest.fn()
const mockSetDisplayPreferences = jest.fn()
const mockResetSettings = jest.fn()

const mockStoreState = {
  region: 'us_ct',
  utilityTypes: ['electricity'] as string[],
  currentSupplier: null as null | { id: string; name: string; estimatedAnnualCost: number },
  annualUsageKwh: 10500,
  peakDemandKw: 5.0,
  notificationPreferences: { priceAlerts: true, optimalTimes: true, supplierUpdates: false },
  displayPreferences: { currency: 'USD', theme: 'light', timeFormat: '24h' },
  setRegion: mockSetRegion,
  setUtilityTypes: mockSetUtilityTypes,
  setCurrentSupplier: mockSetCurrentSupplierStore,
  setAnnualUsage: mockSetAnnualUsage,
  setPeakDemand: mockSetPeakDemand,
  setNotificationPreferences: mockSetNotificationPreferences,
  setDisplayPreferences: mockSetDisplayPreferences,
  resetSettings: mockResetSettings,
}

jest.mock('@/lib/store/settings', () => ({
  // Settings page calls useSettingsStore() without a selector — return full state
  useSettingsStore: (selector?: (s: Record<string, unknown>) => unknown) =>
    selector ? selector(mockStoreState as Record<string, unknown>) : mockStoreState,
}))

// --- Hook mocks ---
const mockUpdateProfile = jest.fn()
const mockSetSupplier = jest.fn()
const mockLinkAccount = jest.fn()

jest.mock('@/lib/hooks/useProfile', () => ({
  useUpdateProfile: () => ({ mutateAsync: mockUpdateProfile, isPending: false }),
}))

jest.mock('@/lib/hooks/useSuppliers', () => ({
  useSuppliers: () => ({ data: { suppliers: [] } }),
  useSetSupplier: () => ({ mutateAsync: mockSetSupplier }),
  useLinkAccount: () => ({ mutateAsync: mockLinkAccount, isPending: false }),
  useUserSupplierAccounts: () => ({ data: { accounts: [] } }),
}))

// --- Component mocks ---
jest.mock('@/components/layout/Header', () => ({
  Header: ({ title }: { title: string }) => <h1>{title}</h1>,
}))

jest.mock('@/components/suppliers/SupplierSelector', () => ({
  SupplierSelector: () => <div data-testid="supplier-selector">SupplierSelector</div>,
}))

jest.mock('@/components/suppliers/SupplierAccountForm', () => ({
  SupplierAccountForm: () => <div data-testid="supplier-account-form">SupplierAccountForm</div>,
}))

// --- Toast mock ---
const mockToastError = jest.fn()
jest.mock('@/lib/contexts/toast-context', () => ({
  useToast: () => ({
    success: jest.fn(),
    error: mockToastError,
  }),
}))

// --- Constants mock ---
jest.mock('@/lib/constants/regions', () => ({
  US_REGIONS: [
    {
      label: 'Northeast',
      states: [
        { value: 'us_ct', label: 'Connecticut', abbr: 'CT' },
        { value: 'us_ny', label: 'New York', abbr: 'NY' },
      ],
    },
  ],
  DEREGULATED_ELECTRICITY_STATES: new Set(['CT', 'NY']),
}))

// --- Format utils ---
jest.mock('@/lib/utils/format', () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
}))

const mockFetch = global.fetch as jest.Mock

import SettingsPage from '@/app/(app)/settings/page'

describe('SettingsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockStoreState.currentSupplier = null
    mockStoreState.region = 'us_ct'
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({}) })
  })

  it('renders the Settings heading', () => {
    render(<SettingsPage />)
    expect(screen.getByRole('heading', { name: /settings/i })).toBeInTheDocument()
  })

  it('renders Account section', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Account')).toBeInTheDocument()
  })

  it('renders region selector with current region selected', () => {
    render(<SettingsPage />)
    // The select uses option values like 'us_ct' (not the label 'Connecticut')
    // Find the region select by looking for the element that has 'us_ct' as its value
    const selects = document.querySelectorAll('select')
    const regionSelect = Array.from(selects).find(
      s => (s as HTMLSelectElement).value === 'us_ct'
    )
    expect(regionSelect).not.toBeUndefined()
  })

  it('calls setRegion when region changes', async () => {
    const user = userEvent.setup()
    render(<SettingsPage />)

    // Find the region select (has optgroup with Northeast)
    const regionSelect = document.querySelector('select optgroup[label="Northeast"]')?.closest('select')
    expect(regionSelect).not.toBeNull()
    await user.selectOptions(regionSelect as HTMLSelectElement, 'us_ny')
    expect(mockSetRegion).toHaveBeenCalledWith('us_ny')
  })

  it('renders Utility Types section', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Utility Types')).toBeInTheDocument()
  })

  it('renders all utility type options', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Electricity')).toBeInTheDocument()
    expect(screen.getByText('Natural Gas')).toBeInTheDocument()
    expect(screen.getByText('Heating Oil')).toBeInTheDocument()
    expect(screen.getByText('Propane')).toBeInTheDocument()
    expect(screen.getByText('Community Solar')).toBeInTheDocument()
  })

  it('renders SupplierSelector when no current supplier', () => {
    render(<SettingsPage />)
    expect(screen.getByTestId('supplier-selector')).toBeInTheDocument()
  })

  it('renders current supplier info when supplier is set', () => {
    mockStoreState.currentSupplier = {
      id: '1',
      name: 'Eversource Energy',
      estimatedAnnualCost: 1200,
    } as never
    render(<SettingsPage />)

    expect(screen.getByText('Eversource Energy')).toBeInTheDocument()
    expect(screen.getByText(/connected/i)).toBeInTheDocument()
    // Multiple "Change" buttons may exist — at least one is present
    expect(screen.getAllByRole('button', { name: /change/i }).length).toBeGreaterThanOrEqual(1)
  })

  it('shows SupplierSelector when Change button is clicked', async () => {
    mockStoreState.currentSupplier = {
      id: '1',
      name: 'Eversource Energy',
      estimatedAnnualCost: 1200,
    } as never
    const user = userEvent.setup()
    render(<SettingsPage />)

    // Click the first "Change" button (the supplier change button)
    const changeButtons = screen.getAllByRole('button', { name: /change/i })
    await user.click(changeButtons[0])

    expect(screen.getByTestId('supplier-selector')).toBeInTheDocument()
  })

  it('renders Energy Usage section', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Energy Usage')).toBeInTheDocument()
  })

  it('renders annual usage input with current value', () => {
    render(<SettingsPage />)
    const input = screen.getByLabelText(/annual usage/i)
    expect(input).toHaveValue(10500)
  })

  it('renders peak demand input with current value', () => {
    render(<SettingsPage />)
    const input = screen.getByLabelText(/peak demand/i)
    expect(input).toHaveValue(5.0)
  })

  it('renders Notifications section', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Notifications')).toBeInTheDocument()
  })

  it('renders notification checkboxes', () => {
    render(<SettingsPage />)
    expect(screen.getByLabelText(/price alerts/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/optimal time reminders/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/supplier updates/i)).toBeInTheDocument()
  })

  it('renders Display section', () => {
    render(<SettingsPage />)
    expect(screen.getByText('Display')).toBeInTheDocument()
  })

  it('renders currency selector', () => {
    render(<SettingsPage />)
    expect(screen.getByDisplayValue('USD (Dollars)')).toBeInTheDocument()
  })

  it('calls setDisplayPreferences when currency changes', async () => {
    const user = userEvent.setup()
    render(<SettingsPage />)

    // Find currency select by current value
    const selects = screen.getAllByRole('combobox')
    const currencySelect = selects.find(s => (s as HTMLSelectElement).value === 'USD')!
    await user.selectOptions(currencySelect, 'GBP')

    expect(mockSetDisplayPreferences).toHaveBeenCalledWith({ currency: 'GBP' })
  })

  it('renders Privacy and Data section', () => {
    render(<SettingsPage />)
    expect(screen.getAllByText(/privacy & data/i).length).toBeGreaterThanOrEqual(1)
  })

  it('renders Reset Settings button', () => {
    render(<SettingsPage />)
    expect(screen.getByRole('button', { name: /reset/i })).toBeInTheDocument()
  })

  it('calls resetSettings when Reset button is clicked', async () => {
    const user = userEvent.setup()
    render(<SettingsPage />)

    await user.click(screen.getByRole('button', { name: /^reset$/i }))
    expect(mockResetSettings).toHaveBeenCalledTimes(1)
  })

  it('renders Download My Data button', () => {
    render(<SettingsPage />)
    expect(screen.getByRole('button', { name: /download my data/i })).toBeInTheDocument()
  })

  it('renders Delete My Account button', () => {
    render(<SettingsPage />)
    expect(screen.getByRole('button', { name: /delete my account/i })).toBeInTheDocument()
  })

  it('renders Save Changes button', () => {
    render(<SettingsPage />)
    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument()
  })

  it('calls updateProfile.mutateAsync when Save Changes is clicked with a region', async () => {
    const user = userEvent.setup()
    mockUpdateProfile.mockResolvedValue(undefined)
    render(<SettingsPage />)

    await user.click(screen.getByRole('button', { name: /save changes/i }))

    await waitFor(() => {
      expect(mockUpdateProfile).toHaveBeenCalledWith({ region: 'us_ct' })
    })
  })

  it('shows Settings saved confirmation after successful save', async () => {
    const user = userEvent.setup()
    mockUpdateProfile.mockResolvedValue(undefined)
    render(<SettingsPage />)

    await user.click(screen.getByRole('button', { name: /save changes/i }))

    await waitFor(() => {
      expect(screen.getByText(/settings saved/i)).toBeInTheDocument()
    })
  })

  it('shows toast error when save fails', async () => {
    const user = userEvent.setup()
    mockUpdateProfile.mockRejectedValue(new Error('Save failed'))
    render(<SettingsPage />)

    await user.click(screen.getByRole('button', { name: /save changes/i }))

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Save failed', expect.any(String))
    })
  })

  it('calls GDPR export endpoint and triggers download', async () => {
    const mockCreateObjectURL = jest.fn(() => 'blob:test')
    const mockRevokeObjectURL = jest.fn()
    global.URL.createObjectURL = mockCreateObjectURL
    global.URL.revokeObjectURL = mockRevokeObjectURL

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ user: 'data' }),
    })

    const user = userEvent.setup()
    render(<SettingsPage />)

    await user.click(screen.getByRole('button', { name: /download my data/i }))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/v1/compliance/gdpr/export', { credentials: 'include' })
    })
    // Verify a blob URL was created from the response data
    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalledTimes(1)
    })
  })

  it('shows toast error when export fails', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false })
    const user = userEvent.setup()
    render(<SettingsPage />)

    await user.click(screen.getByRole('button', { name: /download my data/i }))

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Export failed', expect.any(String))
    })
  })

  it('calls delete endpoint when Delete My Account is confirmed', async () => {
    jest.spyOn(window, 'confirm').mockReturnValueOnce(true)
    mockFetch.mockResolvedValueOnce({ ok: true })

    const user = userEvent.setup()
    render(<SettingsPage />)

    await user.click(screen.getByRole('button', { name: /delete my account/i }))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/compliance/gdpr/delete',
        { method: 'DELETE', credentials: 'include' }
      )
    })
  })

  it('does not call delete endpoint when Delete is cancelled', async () => {
    jest.spyOn(window, 'confirm').mockReturnValueOnce(false)
    const user = userEvent.setup()
    render(<SettingsPage />)

    await user.click(screen.getByRole('button', { name: /delete my account/i }))

    expect(mockFetch).not.toHaveBeenCalled()
  })
})
