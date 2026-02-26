'use client'

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { Appliance, Supplier, UserSettings } from '@/types'

export type UtilityType = 'electricity' | 'natural_gas' | 'heating_oil' | 'propane' | 'community_solar'

interface PriceAlert {
  id: string
  type: 'below' | 'above'
  threshold: number
  enabled: boolean
}

interface SettingsState {
  // User settings
  region: string | null
  utilityTypes: UtilityType[]
  currentSupplier: Supplier | null
  annualUsageKwh: number
  peakDemandKw: number
  appliances: Appliance[]
  priceAlerts: PriceAlert[]

  // Notification preferences
  notificationPreferences: {
    priceAlerts: boolean
    optimalTimes: boolean
    supplierUpdates: boolean
  }

  // Display preferences
  displayPreferences: {
    currency: 'GBP' | 'EUR' | 'USD'
    theme: 'light' | 'dark' | 'system'
    timeFormat: '12h' | '24h'
  }

  // Actions
  setRegion: (region: string | null) => void
  setUtilityTypes: (types: UtilityType[]) => void
  setCurrentSupplier: (supplier: Supplier | null) => void
  setAnnualUsage: (usage: number) => void
  setPeakDemand: (demand: number) => void
  setAppliances: (appliances: Appliance[]) => void
  addAppliance: (appliance: Appliance) => void
  updateAppliance: (id: string, updates: Partial<Appliance>) => void
  removeAppliance: (id: string) => void
  addPriceAlert: (alert: PriceAlert) => void
  removePriceAlert: (id: string) => void
  togglePriceAlert: (id: string) => void
  setNotificationPreferences: (
    prefs: Partial<SettingsState['notificationPreferences']>
  ) => void
  setDisplayPreferences: (
    prefs: Partial<SettingsState['displayPreferences']>
  ) => void
  resetSettings: () => void
}

const defaultSettings: Omit<
  SettingsState,
  | 'setRegion'
  | 'setUtilityTypes'
  | 'setCurrentSupplier'
  | 'setAnnualUsage'
  | 'setPeakDemand'
  | 'setAppliances'
  | 'addAppliance'
  | 'updateAppliance'
  | 'removeAppliance'
  | 'addPriceAlert'
  | 'removePriceAlert'
  | 'togglePriceAlert'
  | 'setNotificationPreferences'
  | 'setDisplayPreferences'
  | 'resetSettings'
> = {
  region: null,
  utilityTypes: ['electricity'] as UtilityType[],
  currentSupplier: null,
  annualUsageKwh: 10500, // US average
  peakDemandKw: 5,
  appliances: [],
  priceAlerts: [] as PriceAlert[],
  notificationPreferences: {
    priceAlerts: true,
    optimalTimes: true,
    supplierUpdates: false,
  },
  displayPreferences: {
    currency: 'USD',
    theme: 'system',
    timeFormat: '12h',
  },
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      ...defaultSettings,

      setRegion: (region) => set({ region }),

      setUtilityTypes: (types) => set({ utilityTypes: types }),

      setCurrentSupplier: (supplier) => set({ currentSupplier: supplier }),

      setAnnualUsage: (usage) => set({ annualUsageKwh: usage }),

      setPeakDemand: (demand) => set({ peakDemandKw: demand }),

      setAppliances: (appliances) => set({ appliances }),

      addAppliance: (appliance) =>
        set((state) => ({
          appliances: [...state.appliances, appliance],
        })),

      updateAppliance: (id, updates) =>
        set((state) => ({
          appliances: state.appliances.map((a) =>
            a.id === id ? { ...a, ...updates } : a
          ),
        })),

      removeAppliance: (id) =>
        set((state) => ({
          appliances: state.appliances.filter((a) => a.id !== id),
        })),

      addPriceAlert: (alert) =>
        set((state) => ({
          priceAlerts: [...state.priceAlerts, alert],
        })),

      removePriceAlert: (id) =>
        set((state) => ({
          priceAlerts: state.priceAlerts.filter((a) => a.id !== id),
        })),

      togglePriceAlert: (id) =>
        set((state) => ({
          priceAlerts: state.priceAlerts.map((a) =>
            a.id === id ? { ...a, enabled: !a.enabled } : a
          ),
        })),

      setNotificationPreferences: (prefs) =>
        set((state) => ({
          notificationPreferences: {
            ...state.notificationPreferences,
            ...prefs,
          },
        })),

      setDisplayPreferences: (prefs) =>
        set((state) => ({
          displayPreferences: {
            ...state.displayPreferences,
            ...prefs,
          },
        })),

      resetSettings: () => set(defaultSettings),
    }),
    {
      name: 'electricity-optimizer-settings',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        region: state.region,
        utilityTypes: state.utilityTypes,
        currentSupplier: state.currentSupplier,
        annualUsageKwh: state.annualUsageKwh,
        peakDemandKw: state.peakDemandKw,
        appliances: state.appliances,
        priceAlerts: state.priceAlerts,
        notificationPreferences: state.notificationPreferences,
        displayPreferences: state.displayPreferences,
      }),
    }
  )
)

// Selector hooks for specific parts of state
export const useRegion = () => useSettingsStore((s) => s.region)
export const useUtilityTypes = () => useSettingsStore((s) => s.utilityTypes)
export const useCurrentSupplier = () => useSettingsStore((s) => s.currentSupplier)
export const useAnnualUsage = () => useSettingsStore((s) => s.annualUsageKwh)
export const useAppliances = () => useSettingsStore((s) => s.appliances)
export const useCurrency = () =>
  useSettingsStore((s) => s.displayPreferences.currency)
export const useTheme = () => useSettingsStore((s) => s.displayPreferences.theme)
export const usePriceAlerts = () => useSettingsStore((s) => s.priceAlerts)

export type { PriceAlert }
