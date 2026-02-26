import { renderHook, waitFor, act } from '@testing-library/react'
import React, { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

// --- Mocks ---

const mockGetSuppliers = jest.fn()
const mockGetSupplier = jest.fn()
const mockGetRecommendation = jest.fn()
const mockCompareSuppliers = jest.fn()
const mockInitiateSwitch = jest.fn()
const mockGetSwitchStatus = jest.fn()
const mockSetUserSupplier = jest.fn()
const mockGetUserSupplier = jest.fn()
const mockRemoveUserSupplier = jest.fn()
const mockLinkSupplierAccount = jest.fn()
const mockGetUserSupplierAccounts = jest.fn()
const mockUnlinkSupplierAccount = jest.fn()

jest.mock('@/lib/api/suppliers', () => ({
  getSuppliers: (...args: unknown[]) => mockGetSuppliers(...args),
  getSupplier: (...args: unknown[]) => mockGetSupplier(...args),
  getRecommendation: (...args: unknown[]) => mockGetRecommendation(...args),
  compareSuppliers: (...args: unknown[]) => mockCompareSuppliers(...args),
  initiateSwitch: (...args: unknown[]) => mockInitiateSwitch(...args),
  getSwitchStatus: (...args: unknown[]) => mockGetSwitchStatus(...args),
  setUserSupplier: (...args: unknown[]) => mockSetUserSupplier(...args),
  getUserSupplier: (...args: unknown[]) => mockGetUserSupplier(...args),
  removeUserSupplier: (...args: unknown[]) => mockRemoveUserSupplier(...args),
  linkSupplierAccount: (...args: unknown[]) => mockLinkSupplierAccount(...args),
  getUserSupplierAccounts: (...args: unknown[]) =>
    mockGetUserSupplierAccounts(...args),
  unlinkSupplierAccount: (...args: unknown[]) =>
    mockUnlinkSupplierAccount(...args),
}))

import {
  useSuppliers,
  useSupplier,
  useSupplierRecommendation,
  useCompareSuppliers,
  useInitiateSwitch,
  useSwitchStatus,
  useUserSupplier,
  useSetSupplier,
  useRemoveSupplier,
  useLinkAccount,
  useUserSupplierAccounts,
  useUnlinkAccount,
} from '@/lib/hooks/useSuppliers'

// --- Helpers ---

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  })
  return {
    queryClient,
    wrapper: ({ children }: { children: ReactNode }) =>
      React.createElement(
        QueryClientProvider,
        { client: queryClient },
        children
      ),
  }
}

// --- Mock data ---

const mockSuppliersData = {
  suppliers: [
    {
      id: 'sup-1',
      name: 'Eversource Energy',
      avgPricePerKwh: 0.24,
      standingCharge: 9.99,
      greenEnergy: false,
      rating: 3.8,
      estimatedAnnualCost: 2520,
      tariffType: 'variable',
    },
    {
      id: 'sup-2',
      name: 'United Illuminating',
      avgPricePerKwh: 0.22,
      standingCharge: 8.5,
      greenEnergy: true,
      rating: 4.1,
      estimatedAnnualCost: 2310,
      tariffType: 'fixed',
    },
  ],
}

const mockSingleSupplier = {
  id: 'sup-1',
  name: 'Eversource Energy',
  avgPricePerKwh: 0.24,
  standingCharge: 9.99,
  greenEnergy: false,
  rating: 3.8,
}

const mockRecommendation = {
  recommendation: {
    supplierId: 'sup-2',
    supplierName: 'United Illuminating',
    estimatedSavings: 210,
    reason: 'Lower average kWh rate',
  },
}

// ==========================================================================
// useSuppliers
// ==========================================================================
describe('useSuppliers', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetSuppliers.mockResolvedValue(mockSuppliersData)
  })

  it('fetches suppliers with default region', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSuppliers(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockSuppliersData)
    expect(mockGetSuppliers).toHaveBeenCalledWith('us_ct', undefined)
  })

  it('fetches suppliers with custom region', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSuppliers('us_ny'), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(mockGetSuppliers).toHaveBeenCalledWith('us_ny', undefined)
  })

  it('fetches suppliers with annual usage', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useSuppliers('us_ct', 12000), { wrapper })

    await waitFor(() => {
      expect(mockGetSuppliers).toHaveBeenCalledWith('us_ct', 12000)
    })
  })

  it('uses correct query key with region and usage', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => useSuppliers('us_ma', 8000), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual(['suppliers', 'us_ma', 8000])
    })
  })

  it('handles fetch error', async () => {
    mockGetSuppliers.mockRejectedValue(new Error('API unavailable'))

    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSuppliers(), { wrapper })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error?.message).toBe('API unavailable')
  })

  it('refetches when region changes', async () => {
    const { wrapper } = createWrapper()

    const { rerender } = renderHook(
      ({ region }: { region: string }) => useSuppliers(region),
      {
        wrapper,
        initialProps: { region: 'us_ct' },
      }
    )

    await waitFor(() => {
      expect(mockGetSuppliers).toHaveBeenCalledWith('us_ct', undefined)
    })

    rerender({ region: 'us_ny' })

    await waitFor(() => {
      expect(mockGetSuppliers).toHaveBeenCalledWith('us_ny', undefined)
    })

    expect(mockGetSuppliers).toHaveBeenCalledTimes(2)
  })
})

// ==========================================================================
// useSupplier (single)
// ==========================================================================
describe('useSupplier', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetSupplier.mockResolvedValue(mockSingleSupplier)
  })

  it('fetches a single supplier by ID', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSupplier('sup-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockSingleSupplier)
    expect(mockGetSupplier).toHaveBeenCalledWith('sup-1')
  })

  it('is disabled when supplierId is empty', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSupplier(''), { wrapper })

    // Query should not fire
    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetSupplier).not.toHaveBeenCalled()
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => useSupplier('sup-42'), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual(['supplier', 'sup-42'])
    })
  })
})

// ==========================================================================
// useSupplierRecommendation
// ==========================================================================
describe('useSupplierRecommendation', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetRecommendation.mockResolvedValue(mockRecommendation)
  })

  it('fetches recommendation with valid params', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => useSupplierRecommendation('sup-1', 10500, 'us_ct'),
      { wrapper }
    )

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual(mockRecommendation)
    expect(mockGetRecommendation).toHaveBeenCalledWith('sup-1', 10500, 'us_ct')
  })

  it('is disabled when currentSupplierId is empty', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => useSupplierRecommendation('', 10500),
      { wrapper }
    )

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetRecommendation).not.toHaveBeenCalled()
  })

  it('is disabled when annualUsage is 0', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => useSupplierRecommendation('sup-1', 0),
      { wrapper }
    )

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetRecommendation).not.toHaveBeenCalled()
  })

  it('uses default region us_ct', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useSupplierRecommendation('sup-1', 10000), { wrapper })

    await waitFor(() => {
      expect(mockGetRecommendation).toHaveBeenCalledWith(
        'sup-1',
        10000,
        'us_ct'
      )
    })
  })
})

// ==========================================================================
// useCompareSuppliers
// ==========================================================================
describe('useCompareSuppliers', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCompareSuppliers.mockResolvedValue({
      comparisons: [mockSingleSupplier],
    })
  })

  it('compares suppliers with valid params', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => useCompareSuppliers(['sup-1', 'sup-2'], 10000),
      { wrapper }
    )

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(mockCompareSuppliers).toHaveBeenCalledWith(
      ['sup-1', 'sup-2'],
      10000
    )
  })

  it('is disabled when supplierIds is empty', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useCompareSuppliers([], 10000), {
      wrapper,
    })

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockCompareSuppliers).not.toHaveBeenCalled()
  })

  it('is disabled when annualUsage is 0', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(
      () => useCompareSuppliers(['sup-1'], 0),
      { wrapper }
    )

    expect(result.current.fetchStatus).toBe('idle')
  })
})

// ==========================================================================
// useInitiateSwitch
// ==========================================================================
describe('useInitiateSwitch', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockInitiateSwitch.mockResolvedValue({
      success: true,
      referenceNumber: 'SW-123',
      estimatedCompletionDate: '2026-03-15',
    })
  })

  it('initiates a switch and invalidates queries on success', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useInitiateSwitch(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        newSupplierId: 'sup-2',
        gdprConsent: true,
        currentSupplierId: 'sup-1',
      })
    })

    expect(mockInitiateSwitch).toHaveBeenCalledWith({
      newSupplierId: 'sup-2',
      gdprConsent: true,
      currentSupplierId: 'sup-1',
    })

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['suppliers'] })
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['recommendation'] })
    )
  })

  it('handles switch failure', async () => {
    mockInitiateSwitch.mockRejectedValue(new Error('Switch failed'))

    const { wrapper } = createWrapper()
    const { result } = renderHook(() => useInitiateSwitch(), { wrapper })

    await expect(
      act(async () => {
        await result.current.mutateAsync({
          newSupplierId: 'sup-2',
          gdprConsent: true,
        })
      })
    ).rejects.toThrow('Switch failed')
  })
})

// ==========================================================================
// useSwitchStatus
// ==========================================================================
describe('useSwitchStatus', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetSwitchStatus.mockResolvedValue({
      status: 'processing',
      estimatedCompletionDate: '2026-03-15',
      lastUpdated: '2026-02-25T10:00:00Z',
    })
  })

  it('fetches switch status by reference number', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSwitchStatus('SW-123'), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data?.status).toBe('processing')
    expect(mockGetSwitchStatus).toHaveBeenCalledWith('SW-123')
  })

  it('is disabled when referenceNumber is empty', () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useSwitchStatus(''), { wrapper })

    expect(result.current.fetchStatus).toBe('idle')
    expect(mockGetSwitchStatus).not.toHaveBeenCalled()
  })
})

// ==========================================================================
// useUserSupplier
// ==========================================================================
describe('useUserSupplier', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetUserSupplier.mockResolvedValue({
      supplier: {
        supplier_id: 'sup-1',
        supplier_name: 'Eversource Energy',
        regions: ['us_ct'],
        rating: 3.8,
        green_energy: false,
        website: 'https://eversource.com',
      },
    })
  })

  it('fetches the current user supplier', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useUserSupplier(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data?.supplier?.supplier_name).toBe(
      'Eversource Energy'
    )
    expect(mockGetUserSupplier).toHaveBeenCalled()
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => useUserSupplier(), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual(['user-supplier'])
    })
  })
})

// ==========================================================================
// useSetSupplier
// ==========================================================================
describe('useSetSupplier', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockSetUserSupplier.mockResolvedValue({
      supplier_id: 'sup-2',
      supplier_name: 'United Illuminating',
      regions: ['us_ct'],
      rating: 4.1,
      green_energy: true,
      website: null,
    })
  })

  it('sets supplier and invalidates queries', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useSetSupplier(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync('sup-2')
    })

    expect(mockSetUserSupplier).toHaveBeenCalledWith('sup-2')
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['user-supplier'] })
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['suppliers'] })
    )
  })
})

// ==========================================================================
// useRemoveSupplier
// ==========================================================================
describe('useRemoveSupplier', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockRemoveUserSupplier.mockResolvedValue({ message: 'Supplier removed' })
  })

  it('removes supplier and invalidates queries', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useRemoveSupplier(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync()
    })

    expect(mockRemoveUserSupplier).toHaveBeenCalled()
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['user-supplier'] })
    )
  })
})

// ==========================================================================
// useLinkAccount
// ==========================================================================
describe('useLinkAccount', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockLinkSupplierAccount.mockResolvedValue({
      supplier_id: 'sup-1',
      supplier_name: 'Eversource',
      account_number_masked: '****1234',
      meter_number_masked: null,
      service_zip: '06103',
      account_nickname: 'Home',
      is_primary: true,
      verified_at: null,
      created_at: '2026-02-25T10:00:00Z',
    })
  })

  it('links an account and invalidates queries', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useLinkAccount(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        supplier_id: 'sup-1',
        account_number: '12345678',
        service_zip: '06103',
        account_nickname: 'Home',
        consent_given: true,
      })
    })

    expect(mockLinkSupplierAccount).toHaveBeenCalledWith({
      supplier_id: 'sup-1',
      account_number: '12345678',
      service_zip: '06103',
      account_nickname: 'Home',
      consent_given: true,
    })

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['user-supplier-accounts'] })
    )
  })
})

// ==========================================================================
// useUserSupplierAccounts
// ==========================================================================
describe('useUserSupplierAccounts', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetUserSupplierAccounts.mockResolvedValue({
      accounts: [
        {
          supplier_id: 'sup-1',
          supplier_name: 'Eversource',
          account_number_masked: '****1234',
          is_primary: true,
        },
      ],
    })
  })

  it('fetches linked accounts', async () => {
    const { wrapper } = createWrapper()

    const { result } = renderHook(() => useUserSupplierAccounts(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data?.accounts).toHaveLength(1)
    expect(result.current.data?.accounts[0].supplier_name).toBe('Eversource')
  })

  it('uses correct query key', async () => {
    const { wrapper, queryClient } = createWrapper()

    renderHook(() => useUserSupplierAccounts(), { wrapper })

    await waitFor(() => {
      const queries = queryClient.getQueryCache().getAll()
      const keys = queries.map((q) => q.queryKey)
      expect(keys).toContainEqual(['user-supplier-accounts'])
    })
  })
})

// ==========================================================================
// useUnlinkAccount
// ==========================================================================
describe('useUnlinkAccount', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUnlinkSupplierAccount.mockResolvedValue({ message: 'Account unlinked' })
  })

  it('unlinks an account and invalidates queries', async () => {
    const { wrapper, queryClient } = createWrapper()
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useUnlinkAccount(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync('sup-1')
    })

    expect(mockUnlinkSupplierAccount).toHaveBeenCalledWith('sup-1')
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['user-supplier-accounts'] })
    )
  })
})
