'use client'

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { Appliance, Supplier, UserSettings } from '@/types'

interface SettingsState {
  // User settings
  region: string
  currentSupplier: Supplier | null
  annualUsageKwh: number
  peakDemandKw: number
  appliances: Appliance[]

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
  setRegion: (region: string) => void
  setCurrentSupplier: (supplier: Supplier | null) => void
  setAnnualUsage: (usage: number) => void
  setPeakDemand: (demand: number) => void
  setAppliances: (appliances: Appliance[]) => void
  addAppliance: (appliance: Appliance) => void
  updateAppliance: (id: string, updates: Partial<Appliance>) => void
  removeAppliance: (id: string) => void
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
  | 'setCurrentSupplier'
  | 'setAnnualUsage'
  | 'setPeakDemand'
  | 'setAppliances'
  | 'addAppliance'
  | 'updateAppliance'
  | 'removeAppliance'
  | 'setNotificationPreferences'
  | 'setDisplayPreferences'
  | 'resetSettings'
> = {
  region: 'us_ct',
  currentSupplier: null,
  annualUsageKwh: 10500, // US average
  peakDemandKw: 5,
  appliances: [],
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
        currentSupplier: state.currentSupplier,
        annualUsageKwh: state.annualUsageKwh,
        peakDemandKw: state.peakDemandKw,
        appliances: state.appliances,
        notificationPreferences: state.notificationPreferences,
        displayPreferences: state.displayPreferences,
      }),
    }
  )
)

// Selector hooks for specific parts of state
export const useRegion = () => useSettingsStore((s) => s.region)
export const useCurrentSupplier = () => useSettingsStore((s) => s.currentSupplier)
export const useAnnualUsage = () => useSettingsStore((s) => s.annualUsageKwh)
export const useAppliances = () => useSettingsStore((s) => s.appliances)
export const useCurrency = () =>
  useSettingsStore((s) => s.displayPreferences.currency)
export const useTheme = () => useSettingsStore((s) => s.displayPreferences.theme)
