'use client'

import React from 'react'
import { Header } from '@/components/layout/Header'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Checkbox } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { useSettingsStore } from '@/lib/store/settings'
import { formatCurrency } from '@/lib/utils/format'
import type { UtilityType } from '@/lib/store/settings'
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
  Flame,
  Sun,
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
    setAnnualUsage,
    setPeakDemand,
    setNotificationPreferences,
    setDisplayPreferences,
    resetSettings,
  } = useSettingsStore()

  const [saved, setSaved] = React.useState(false)

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
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
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className="rounded-lg border border-gray-300 px-3 py-2"
                >
                  <optgroup label="Northeast">
                    <option value="us_ct">Connecticut</option>
                    <option value="us_ma">Massachusetts</option>
                    <option value="us_nh">New Hampshire</option>
                    <option value="us_me">Maine</option>
                    <option value="us_ri">Rhode Island</option>
                    <option value="us_vt">Vermont</option>
                    <option value="us_ny">New York</option>
                    <option value="us_nj">New Jersey</option>
                    <option value="us_pa">Pennsylvania</option>
                    <option value="us_de">Delaware</option>
                    <option value="us_md">Maryland</option>
                    <option value="us_dc">District of Columbia</option>
                  </optgroup>
                  <optgroup label="Midwest">
                    <option value="us_oh">Ohio</option>
                    <option value="us_il">Illinois</option>
                    <option value="us_mi">Michigan</option>
                    <option value="us_in">Indiana</option>
                  </optgroup>
                  <optgroup label="South">
                    <option value="us_tx">Texas</option>
                    <option value="us_va">Virginia</option>
                    <option value="us_ga">Georgia</option>
                    <option value="us_fl">Florida</option>
                    <option value="us_ky">Kentucky</option>
                  </optgroup>
                  <optgroup label="West">
                    <option value="us_ca">California</option>
                    <option value="us_or">Oregon</option>
                    <option value="us_mt">Montana</option>
                  </optgroup>
                  <optgroup label="International">
                    <option value="uk">United Kingdom</option>
                    <option value="de">Germany</option>
                    <option value="fr">France</option>
                  </optgroup>
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

              <div className="border-t border-gray-200 pt-4">
                <p className="font-medium text-gray-900">Current Supplier</p>
                {currentSupplier ? (
                  <div className="mt-2 flex items-center justify-between rounded-lg bg-gray-50 p-3">
                    <div>
                      <p className="font-medium">{currentSupplier.name}</p>
                      <p className="text-sm text-gray-500">
                        {formatCurrency(currentSupplier.estimatedAnnualCost)}/year
                      </p>
                    </div>
                    <Badge variant="success">Connected</Badge>
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-gray-500">
                    No supplier connected. Visit the Suppliers page to set one.
                  </p>
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
                  <p className="font-medium text-gray-900">Export Data</p>
                  <p className="text-sm text-gray-500">
                    Download all your data as JSON
                  </p>
                </div>
                <Button variant="outline" size="sm">
                  <Download className="mr-2 h-4 w-4" />
                  Export
                </Button>
              </div>

              <div className="flex items-center justify-between border-t border-gray-200 pt-4">
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
