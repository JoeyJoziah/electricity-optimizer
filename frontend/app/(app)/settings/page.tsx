'use client'

import React from 'react'
import { Header } from '@/components/layout/Header'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Checkbox } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { SupplierSelector } from '@/components/suppliers/SupplierSelector'
import { SupplierAccountForm } from '@/components/suppliers/SupplierAccountForm'
import { useSettingsStore } from '@/lib/store/settings'
import { useSuppliers, useSetSupplier, useLinkAccount, useUserSupplierAccounts } from '@/lib/hooks/useSuppliers'
import { useUpdateProfile } from '@/lib/hooks/useProfile'
import { formatCurrency } from '@/lib/utils/format'
import { US_REGIONS, DEREGULATED_ELECTRICITY_STATES } from '@/lib/constants/regions'
import type { UtilityType } from '@/lib/store/settings'
import type { Supplier, RawSupplierRecord } from '@/types'
import type { LinkedAccountResponse } from '@/lib/api/suppliers'
import { useToast } from '@/lib/contexts/toast-context'
import {
  User,
  MapPin,
  Zap,
  Bell,
  Palette,
  Shield,
  Download,
  Trash2,
  Save,
  CheckCircle,
  Link2,
  X,
} from 'lucide-react'

const UTILITY_TYPE_OPTIONS: { value: UtilityType; label: string }[] = [
  { value: 'electricity', label: 'Electricity' },
  { value: 'natural_gas', label: 'Natural Gas' },
  { value: 'heating_oil', label: 'Heating Oil' },
  { value: 'propane', label: 'Propane' },
  { value: 'community_solar', label: 'Community Solar' },
]

export default function SettingsPage() {
  const {
    region,
    utilityTypes,
    currentSupplier,
    annualUsageKwh,
    peakDemandKw,
    notificationPreferences,
    displayPreferences,
    setRegion,
    setUtilityTypes,
    setCurrentSupplier: setCurrentSupplierStore,
    setAnnualUsage,
    setPeakDemand,
    setNotificationPreferences,
    setDisplayPreferences,
    resetSettings,
  } = useSettingsStore()

  const { success: toastSuccess, error: toastError } = useToast()
  const [saved, setSaved] = React.useState(false)
  const [exporting, setExporting] = React.useState(false)
  const [showSupplierPicker, setShowSupplierPicker] = React.useState(false)

  const updateProfileMutation = useUpdateProfile()

  // Fetch suppliers for the region
  const { data: suppliersData } = useSuppliers(region || '', annualUsageKwh)
  const setSupplierMutation = useSetSupplier()
  const linkAccountMutation = useLinkAccount()
  const { data: accountsData } = useUserSupplierAccounts()

  // Map backend suppliers to frontend type
  const availableSuppliers: Supplier[] = (suppliersData?.suppliers || []).map((s: RawSupplierRecord) => ({
    id: s.id,
    name: s.name,
    logo: s.logo || s.logo_url,
    avgPricePerKwh: s.avgPricePerKwh ?? 0.22,
    standingCharge: s.standingCharge ?? 0.40,
    greenEnergy: s.greenEnergy ?? s.green_energy_provider ?? false,
    rating: s.rating ?? 0,
    estimatedAnnualCost: s.estimatedAnnualCost ?? Math.round((s.avgPricePerKwh ?? 0.22) * annualUsageKwh + 365 * 0.40),
    tariffType: (s.tariffType ?? (s.tariff_types?.[0] || 'variable')) as Supplier['tariffType'],
    exitFee: s.exitFee ?? s.exit_fee,
    contractLength: s.contractLength ?? s.contract_length,
    features: s.features ?? s.tariff_types,
  }))

  const linkedAccounts = accountsData?.accounts || []

  const handleSupplierChange = async (supplier: Supplier | null) => {
    if (!supplier) return

    try {
      await setSupplierMutation.mutateAsync(supplier.id)
    } catch {
      // Backend save failed — still update local state
    }

    setCurrentSupplierStore(supplier)
    setShowSupplierPicker(false)
  }

  const handleLinkAccount = async (data: {
    supplierId: string
    accountNumber: string
    meterNumber?: string
    serviceZip?: string
    accountNickname?: string
    consentGiven: boolean
  }) => {
    await linkAccountMutation.mutateAsync({
      supplier_id: data.supplierId,
      account_number: data.accountNumber,
      meter_number: data.meterNumber,
      service_zip: data.serviceZip,
      account_nickname: data.accountNickname,
      consent_given: data.consentGiven,
    })
  }

  const handleSave = async () => {
    try {
      if (region) {
        await updateProfileMutation.mutateAsync({ region })
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      toastError('Save failed', 'Could not save settings to server.')
    }
  }

  const handleExportData = async () => {
    setExporting(true)
    try {
      const res = await fetch('/api/v1/compliance/gdpr/export', { credentials: 'include' })
      if (!res.ok) throw new Error('Export failed')
      const data = await res.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `my-data-${new Date().toISOString().split('T')[0]}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toastError('Export failed', 'Please try again later.')
    } finally {
      setExporting(false)
    }
  }

  const handleDeleteAccount = async () => {
    const confirmed = window.confirm(
      'Are you sure you want to delete your account? This action is irreversible and will permanently delete all your data.'
    )
    if (!confirmed) return
    try {
      const res = await fetch('/api/v1/compliance/gdpr/delete', { method: 'DELETE', credentials: 'include' })
      if (!res.ok) throw new Error('Delete failed')
      window.location.href = '/'
    } catch {
      toastError('Delete failed', 'Please try again later.')
    }
  }

  return (
    <div className="flex flex-col">
      <Header title="Settings" />

      <div className="p-6">
        <div className="mx-auto max-w-3xl space-y-6">
          {/* Account settings */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="h-5 w-5" />
                Account
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-900">Region</p>
                  <p className="text-sm text-gray-500">
                    Your energy market region
                  </p>
                </div>
                <select
                  value={region || ''}
                  onChange={(e) => setRegion(e.target.value)}
                  className="rounded-lg border border-gray-300 px-3 py-2"
                >
                  <option value="" disabled>Select your state...</option>
                  {US_REGIONS.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.states.map((state) => (
                        <option key={state.value} value={state.value}>
                          {state.label}
                          {DEREGULATED_ELECTRICITY_STATES.has(state.abbr) ? ' *' : ''}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              <div className="border-t border-gray-200 pt-4">
                <p className="font-medium text-gray-900">Utility Types</p>
                <p className="mb-3 text-sm text-gray-500">
                  Select the energy types you want to compare
                </p>
                <div className="flex flex-wrap gap-2">
                  {UTILITY_TYPE_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                        utilityTypes.includes(opt.value)
                          ? 'border-primary-500 bg-primary-50 text-primary-700'
                          : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={utilityTypes.includes(opt.value)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setUtilityTypes([...utilityTypes, opt.value])
                          } else {
                            const next = utilityTypes.filter((t) => t !== opt.value)
                            if (next.length > 0) setUtilityTypes(next)
                          }
                        }}
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
              </div>

              {/* Interactive Current Supplier section */}
              <div className="border-t border-gray-200 pt-4">
                <p className="font-medium text-gray-900">Current Supplier</p>
                {currentSupplier && !showSupplierPicker ? (
                  <div className="mt-2 space-y-3">
                    <div className="flex items-center justify-between rounded-lg bg-gray-50 p-3">
                      <div>
                        <p className="font-medium">{currentSupplier.name}</p>
                        <p className="text-sm text-gray-500">
                          {formatCurrency(currentSupplier.estimatedAnnualCost)}/year
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="success">Connected</Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setShowSupplierPicker(true)}
                        >
                          Change
                        </Button>
                      </div>
                    </div>

                    {/* Linked account info */}
                    {linkedAccounts.length > 0 && (
                      <div className="space-y-2">
                        {linkedAccounts.map((account: LinkedAccountResponse) => (
                          <div
                            key={account.supplier_id}
                            className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm"
                          >
                            <div>
                              <span className="text-gray-500">Account: </span>
                              <span className="font-mono">{account.account_number_masked || 'Linked'}</span>
                              {account.account_nickname && (
                                <span className="ml-2 text-gray-400">({account.account_nickname})</span>
                              )}
                            </div>
                            <Badge variant="info" size="sm">
                              <Link2 className="mr-1 h-3 w-3" />
                              Linked
                            </Badge>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Link account form */}
                    <SupplierAccountForm
                      supplierId={currentSupplier.id}
                      supplierName={currentSupplier.name}
                      onSubmit={handleLinkAccount}
                      isLoading={linkAccountMutation.isPending}
                    />
                  </div>
                ) : (
                  <div className="mt-2">
                    {showSupplierPicker && (
                      <div className="mb-2 flex justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setShowSupplierPicker(false)}
                        >
                          <X className="mr-1 h-3 w-3" />
                          Cancel
                        </Button>
                      </div>
                    )}
                    <SupplierSelector
                      suppliers={availableSuppliers}
                      value={currentSupplier}
                      onChange={handleSupplierChange}
                      placeholder="Select your current supplier..."
                    />
                    {!currentSupplier && !showSupplierPicker && (
                      <p className="mt-2 text-sm text-gray-500">
                        Select your supplier to get personalized savings recommendations.
                      </p>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Energy usage */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5" />
                Energy Usage
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                label="Annual Usage (kWh)"
                type="number"
                value={annualUsageKwh}
                onChange={(e) => setAnnualUsage(parseInt(e.target.value) || 0)}
                helperText="US average is around 10,500 kWh per year"
              />

              <Input
                label="Peak Demand (kW)"
                type="number"
                step="0.1"
                value={peakDemandKw}
                onChange={(e) => setPeakDemand(parseFloat(e.target.value) || 0)}
                helperText="Maximum power draw at any time"
              />
            </CardContent>
          </Card>

          {/* Notifications */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Notifications
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Checkbox
                label="Price Alerts"
                checked={notificationPreferences.priceAlerts}
                onChange={(e) =>
                  setNotificationPreferences({ priceAlerts: e.target.checked })
                }
              />
              <p className="ml-6 text-sm text-gray-500">
                Get notified when prices drop below your threshold
              </p>

              <Checkbox
                label="Optimal Time Reminders"
                checked={notificationPreferences.optimalTimes}
                onChange={(e) =>
                  setNotificationPreferences({ optimalTimes: e.target.checked })
                }
              />
              <p className="ml-6 text-sm text-gray-500">
                Remind you when it's a good time to run appliances
              </p>

              <Checkbox
                label="Supplier Updates"
                checked={notificationPreferences.supplierUpdates}
                onChange={(e) =>
                  setNotificationPreferences({
                    supplierUpdates: e.target.checked,
                  })
                }
              />
              <p className="ml-6 text-sm text-gray-500">
                Get notified about better supplier deals
              </p>
            </CardContent>
          </Card>

          {/* Display preferences */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette className="h-5 w-5" />
                Display
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-900">Currency</p>
                  <p className="text-sm text-gray-500">
                    Display currency for prices
                  </p>
                </div>
                <select
                  value={displayPreferences.currency}
                  onChange={(e) =>
                    setDisplayPreferences({
                      currency: e.target.value as 'USD' | 'GBP' | 'EUR',
                    })
                  }
                  className="rounded-lg border border-gray-300 px-3 py-2"
                >
                  <option value="USD">USD (Dollars)</option>
                  <option value="GBP">GBP (Pounds)</option>
                  <option value="EUR">EUR (Euros)</option>
                </select>
              </div>

              <div className="flex items-center justify-between border-t border-gray-200 pt-4">
                <div>
                  <p className="font-medium text-gray-900">Theme</p>
                  <p className="text-sm text-gray-500">
                    Application color theme
                  </p>
                </div>
                <select
                  value={displayPreferences.theme}
                  onChange={(e) =>
                    setDisplayPreferences({
                      theme: e.target.value as 'light' | 'dark' | 'system',
                    })
                  }
                  className="rounded-lg border border-gray-300 px-3 py-2"
                >
                  <option value="light">Light</option>
                  <option value="dark">Dark</option>
                  <option value="system">System</option>
                </select>
              </div>

              <div className="flex items-center justify-between border-t border-gray-200 pt-4">
                <div>
                  <p className="font-medium text-gray-900">Time Format</p>
                  <p className="text-sm text-gray-500">
                    How times are displayed
                  </p>
                </div>
                <select
                  value={displayPreferences.timeFormat}
                  onChange={(e) =>
                    setDisplayPreferences({
                      timeFormat: e.target.value as '12h' | '24h',
                    })
                  }
                  className="rounded-lg border border-gray-300 px-3 py-2"
                >
                  <option value="24h">24-hour (14:30)</option>
                  <option value="12h">12-hour (2:30 PM)</option>
                </select>
              </div>
            </CardContent>
          </Card>

          {/* Privacy & Data */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5" />
                Privacy & Data
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-danger-600">Reset Settings</p>
                  <p className="text-sm text-gray-500">
                    Reset all settings to default
                  </p>
                </div>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={resetSettings}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Reset
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Data & Privacy (GDPR) */}
          <div className="mt-8 border-t pt-6">
            <h3 className="text-lg font-semibold text-gray-900">Data & Privacy</h3>
            <p className="mt-1 text-sm text-gray-500">Manage your personal data in accordance with GDPR regulations.</p>
            <div className="mt-4 flex gap-3">
              <Button variant="outline" onClick={handleExportData} disabled={exporting}>
                <Download className="mr-2 h-4 w-4" />
                {exporting ? 'Preparing...' : 'Download My Data'}
              </Button>
              <Button
                variant="danger"
                onClick={handleDeleteAccount}
                className="border-danger-300 text-danger-600 hover:bg-danger-50"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Delete My Account
              </Button>
            </div>
          </div>

          {/* Save button */}
          <div className="flex justify-end gap-4">
            {saved && (
              <div className="flex items-center gap-2 text-success-600">
                <CheckCircle className="h-5 w-5" />
                <span>Settings saved</span>
              </div>
            )}
            <Button variant="primary" onClick={handleSave}>
              <Save className="mr-2 h-4 w-4" />
              Save Changes
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
