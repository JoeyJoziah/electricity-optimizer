'use client'

import React from 'react'
import { Header } from '@/components/layout/Header'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Checkbox } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { useSettingsStore } from '@/lib/store/settings'
import { formatCurrency } from '@/lib/utils/format'
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
} from 'lucide-react'

export default function SettingsPage() {
  const {
    region,
    currentSupplier,
    annualUsageKwh,
    peakDemandKw,
    notificationPreferences,
    displayPreferences,
    setRegion,
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
                    Your electricity market region
                  </p>
                </div>
                <select
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className="rounded-lg border border-gray-300 px-3 py-2"
                >
                  <option value="UK">United Kingdom</option>
                  <option value="EU">Europe</option>
                  <option value="US">United States</option>
                </select>
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
