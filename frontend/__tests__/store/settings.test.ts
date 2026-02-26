import { useSettingsStore, type UtilityType } from '@/lib/store/settings'
import type { Appliance, Supplier } from '@/types'
import '@testing-library/jest-dom'

// Reset store between tests to avoid state leaking
beforeEach(() => {
  const { getState } = useSettingsStore
  getState().resetSettings()
})

describe('useSettingsStore', () => {
  describe('default values', () => {
    test('has correct default region', () => {
      const state = useSettingsStore.getState()
      expect(state.region).toBe('us_ct')
    })

    test('has correct default utility types', () => {
      const state = useSettingsStore.getState()
      expect(state.utilityTypes).toEqual(['electricity'])
    })

    test('has null current supplier by default', () => {
      const state = useSettingsStore.getState()
      expect(state.currentSupplier).toBeNull()
    })

    test('has correct default annual usage', () => {
      const state = useSettingsStore.getState()
      expect(state.annualUsageKwh).toBe(10500)
    })

    test('has correct default peak demand', () => {
      const state = useSettingsStore.getState()
      expect(state.peakDemandKw).toBe(5)
    })

    test('has empty appliances by default', () => {
      const state = useSettingsStore.getState()
      expect(state.appliances).toEqual([])
    })

    test('has empty price alerts by default', () => {
      const state = useSettingsStore.getState()
      expect(state.priceAlerts).toEqual([])
    })

    test('has correct default notification preferences', () => {
      const state = useSettingsStore.getState()
      expect(state.notificationPreferences).toEqual({
        priceAlerts: true,
        optimalTimes: true,
        supplierUpdates: false,
      })
    })

    test('has correct default display preferences', () => {
      const state = useSettingsStore.getState()
      expect(state.displayPreferences).toEqual({
        currency: 'USD',
        theme: 'system',
        timeFormat: '12h',
      })
    })
  })

  describe('setRegion', () => {
    test('updates region', () => {
      useSettingsStore.getState().setRegion('us_ct')
      expect(useSettingsStore.getState().region).toBe('us_ct')
    })

    test('updates region to a different state', () => {
      useSettingsStore.getState().setRegion('us_ny')
      expect(useSettingsStore.getState().region).toBe('us_ny')
    })

    test('updates region to international', () => {
      useSettingsStore.getState().setRegion('gb_london')
      expect(useSettingsStore.getState().region).toBe('gb_london')
    })

    test('does not affect other state properties', () => {
      useSettingsStore.getState().setRegion('us_ca')
      const state = useSettingsStore.getState()
      expect(state.annualUsageKwh).toBe(10500)
      expect(state.currentSupplier).toBeNull()
    })
  })

  describe('setUtilityTypes', () => {
    test('updates utility types', () => {
      const types: UtilityType[] = ['electricity', 'natural_gas']
      useSettingsStore.getState().setUtilityTypes(types)
      expect(useSettingsStore.getState().utilityTypes).toEqual(types)
    })

    test('can set single utility type', () => {
      useSettingsStore.getState().setUtilityTypes(['propane'])
      expect(useSettingsStore.getState().utilityTypes).toEqual(['propane'])
    })

    test('can set all utility types', () => {
      const allTypes: UtilityType[] = [
        'electricity',
        'natural_gas',
        'heating_oil',
        'propane',
        'community_solar',
      ]
      useSettingsStore.getState().setUtilityTypes(allTypes)
      expect(useSettingsStore.getState().utilityTypes).toEqual(allTypes)
    })

    test('can set empty utility types', () => {
      useSettingsStore.getState().setUtilityTypes([])
      expect(useSettingsStore.getState().utilityTypes).toEqual([])
    })
  })

  describe('setCurrentSupplier', () => {
    const mockSupplier: Supplier = {
      id: '1',
      name: 'Eversource Energy',
      avgPricePerKwh: 0.25,
      standingCharge: 0.50,
      greenEnergy: true,
      rating: 4.5,
      estimatedAnnualCost: 1200,
      tariffType: 'variable',
    }

    test('sets supplier from null', () => {
      useSettingsStore.getState().setCurrentSupplier(mockSupplier)
      expect(useSettingsStore.getState().currentSupplier).toEqual(mockSupplier)
    })

    test('clears supplier back to null', () => {
      useSettingsStore.getState().setCurrentSupplier(mockSupplier)
      useSettingsStore.getState().setCurrentSupplier(null)
      expect(useSettingsStore.getState().currentSupplier).toBeNull()
    })

    test('replaces existing supplier', () => {
      const anotherSupplier: Supplier = {
        ...mockSupplier,
        id: '2',
        name: 'NextEra Energy',
        avgPricePerKwh: 0.22,
      }
      useSettingsStore.getState().setCurrentSupplier(mockSupplier)
      useSettingsStore.getState().setCurrentSupplier(anotherSupplier)
      expect(useSettingsStore.getState().currentSupplier?.id).toBe('2')
      expect(useSettingsStore.getState().currentSupplier?.name).toBe('NextEra Energy')
    })
  })

  describe('setAnnualUsage', () => {
    test('updates annual usage', () => {
      useSettingsStore.getState().setAnnualUsage(12000)
      expect(useSettingsStore.getState().annualUsageKwh).toBe(12000)
    })

    test('allows zero usage', () => {
      useSettingsStore.getState().setAnnualUsage(0)
      expect(useSettingsStore.getState().annualUsageKwh).toBe(0)
    })

    test('allows high usage', () => {
      useSettingsStore.getState().setAnnualUsage(50000)
      expect(useSettingsStore.getState().annualUsageKwh).toBe(50000)
    })
  })

  describe('setPeakDemand', () => {
    test('updates peak demand', () => {
      useSettingsStore.getState().setPeakDemand(10)
      expect(useSettingsStore.getState().peakDemandKw).toBe(10)
    })
  })

  describe('appliance management', () => {
    const appliance1: Appliance = {
      id: 'app-1',
      name: 'Dishwasher',
      powerKw: 1.5,
      typicalDurationHours: 1.5,
      isFlexible: true,
      priority: 'medium',
    }

    const appliance2: Appliance = {
      id: 'app-2',
      name: 'Washing Machine',
      powerKw: 0.5,
      typicalDurationHours: 1,
      isFlexible: true,
      priority: 'low',
    }

    test('setAppliances replaces entire list', () => {
      useSettingsStore.getState().setAppliances([appliance1, appliance2])
      expect(useSettingsStore.getState().appliances).toHaveLength(2)
    })

    test('addAppliance appends to list', () => {
      useSettingsStore.getState().addAppliance(appliance1)
      useSettingsStore.getState().addAppliance(appliance2)
      expect(useSettingsStore.getState().appliances).toHaveLength(2)
      expect(useSettingsStore.getState().appliances[0].name).toBe('Dishwasher')
      expect(useSettingsStore.getState().appliances[1].name).toBe('Washing Machine')
    })

    test('updateAppliance modifies specific appliance', () => {
      useSettingsStore.getState().setAppliances([appliance1, appliance2])
      useSettingsStore.getState().updateAppliance('app-1', { name: 'Updated Dishwasher' })
      const appliances = useSettingsStore.getState().appliances
      expect(appliances[0].name).toBe('Updated Dishwasher')
      expect(appliances[0].powerKw).toBe(1.5) // unchanged
      expect(appliances[1].name).toBe('Washing Machine') // unaffected
    })

    test('updateAppliance does not affect non-matching appliance', () => {
      useSettingsStore.getState().setAppliances([appliance1])
      useSettingsStore.getState().updateAppliance('non-existent', { name: 'Ghost' })
      expect(useSettingsStore.getState().appliances[0].name).toBe('Dishwasher')
    })

    test('removeAppliance removes by id', () => {
      useSettingsStore.getState().setAppliances([appliance1, appliance2])
      useSettingsStore.getState().removeAppliance('app-1')
      const appliances = useSettingsStore.getState().appliances
      expect(appliances).toHaveLength(1)
      expect(appliances[0].id).toBe('app-2')
    })

    test('removeAppliance on non-existent id does nothing', () => {
      useSettingsStore.getState().setAppliances([appliance1])
      useSettingsStore.getState().removeAppliance('non-existent')
      expect(useSettingsStore.getState().appliances).toHaveLength(1)
    })
  })

  describe('price alert management', () => {
    const alert1 = { id: 'alert-1', type: 'below' as const, threshold: 0.20, enabled: true }
    const alert2 = { id: 'alert-2', type: 'above' as const, threshold: 0.30, enabled: true }

    test('addPriceAlert adds alert', () => {
      useSettingsStore.getState().addPriceAlert(alert1)
      expect(useSettingsStore.getState().priceAlerts).toHaveLength(1)
      expect(useSettingsStore.getState().priceAlerts[0]).toEqual(alert1)
    })

    test('addPriceAlert appends multiple alerts', () => {
      useSettingsStore.getState().addPriceAlert(alert1)
      useSettingsStore.getState().addPriceAlert(alert2)
      expect(useSettingsStore.getState().priceAlerts).toHaveLength(2)
    })

    test('removePriceAlert removes by id', () => {
      useSettingsStore.getState().addPriceAlert(alert1)
      useSettingsStore.getState().addPriceAlert(alert2)
      useSettingsStore.getState().removePriceAlert('alert-1')
      const alerts = useSettingsStore.getState().priceAlerts
      expect(alerts).toHaveLength(1)
      expect(alerts[0].id).toBe('alert-2')
    })

    test('togglePriceAlert toggles enabled state', () => {
      useSettingsStore.getState().addPriceAlert(alert1)
      expect(useSettingsStore.getState().priceAlerts[0].enabled).toBe(true)

      useSettingsStore.getState().togglePriceAlert('alert-1')
      expect(useSettingsStore.getState().priceAlerts[0].enabled).toBe(false)

      useSettingsStore.getState().togglePriceAlert('alert-1')
      expect(useSettingsStore.getState().priceAlerts[0].enabled).toBe(true)
    })

    test('togglePriceAlert does not affect other alerts', () => {
      useSettingsStore.getState().addPriceAlert(alert1)
      useSettingsStore.getState().addPriceAlert(alert2)
      useSettingsStore.getState().togglePriceAlert('alert-1')
      expect(useSettingsStore.getState().priceAlerts[1].enabled).toBe(true)
    })
  })

  describe('setNotificationPreferences', () => {
    test('updates partial notification preferences', () => {
      useSettingsStore.getState().setNotificationPreferences({ supplierUpdates: true })
      const prefs = useSettingsStore.getState().notificationPreferences
      expect(prefs.supplierUpdates).toBe(true)
      expect(prefs.priceAlerts).toBe(true) // unchanged
      expect(prefs.optimalTimes).toBe(true) // unchanged
    })

    test('updates multiple notification preferences at once', () => {
      useSettingsStore.getState().setNotificationPreferences({
        priceAlerts: false,
        optimalTimes: false,
      })
      const prefs = useSettingsStore.getState().notificationPreferences
      expect(prefs.priceAlerts).toBe(false)
      expect(prefs.optimalTimes).toBe(false)
      expect(prefs.supplierUpdates).toBe(false) // still default
    })
  })

  describe('setDisplayPreferences', () => {
    test('updates currency', () => {
      useSettingsStore.getState().setDisplayPreferences({ currency: 'GBP' })
      expect(useSettingsStore.getState().displayPreferences.currency).toBe('GBP')
    })

    test('updates theme', () => {
      useSettingsStore.getState().setDisplayPreferences({ theme: 'dark' })
      expect(useSettingsStore.getState().displayPreferences.theme).toBe('dark')
    })

    test('updates time format', () => {
      useSettingsStore.getState().setDisplayPreferences({ timeFormat: '24h' })
      expect(useSettingsStore.getState().displayPreferences.timeFormat).toBe('24h')
    })

    test('partial update preserves other display preferences', () => {
      useSettingsStore.getState().setDisplayPreferences({ currency: 'EUR' })
      const prefs = useSettingsStore.getState().displayPreferences
      expect(prefs.currency).toBe('EUR')
      expect(prefs.theme).toBe('system') // unchanged
      expect(prefs.timeFormat).toBe('12h') // unchanged
    })
  })

  describe('resetSettings', () => {
    test('resets all settings to defaults', () => {
      // Modify everything
      useSettingsStore.getState().setRegion('us_ny')
      useSettingsStore.getState().setAnnualUsage(20000)
      useSettingsStore.getState().setPeakDemand(15)
      useSettingsStore.getState().setDisplayPreferences({ currency: 'GBP', theme: 'dark' })
      useSettingsStore.getState().setNotificationPreferences({ priceAlerts: false })
      useSettingsStore.getState().addPriceAlert({
        id: 'x',
        type: 'below',
        threshold: 0.15,
        enabled: true,
      })

      // Reset
      useSettingsStore.getState().resetSettings()

      const state = useSettingsStore.getState()
      expect(state.region).toBe('us_ct')
      expect(state.annualUsageKwh).toBe(10500)
      expect(state.peakDemandKw).toBe(5)
      expect(state.currentSupplier).toBeNull()
      expect(state.appliances).toEqual([])
      expect(state.priceAlerts).toEqual([])
      expect(state.displayPreferences.currency).toBe('USD')
      expect(state.displayPreferences.theme).toBe('system')
      expect(state.notificationPreferences.priceAlerts).toBe(true)
    })
  })

  describe('state isolation', () => {
    test('setting region does not affect display preferences', () => {
      useSettingsStore.getState().setRegion('us_ca')
      expect(useSettingsStore.getState().displayPreferences.currency).toBe('USD')
    })

    test('setting appliances does not affect price alerts', () => {
      const appliance: Appliance = {
        id: 'a',
        name: 'Dryer',
        powerKw: 3,
        typicalDurationHours: 1,
        isFlexible: true,
        priority: 'high',
      }
      useSettingsStore.getState().addAppliance(appliance)
      expect(useSettingsStore.getState().priceAlerts).toEqual([])
    })
  })
})
