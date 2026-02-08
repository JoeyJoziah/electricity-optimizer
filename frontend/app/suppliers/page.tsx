'use client'

import React, { useState } from 'react'
import { Header } from '@/components/layout/Header'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ComparisonTable } from '@/components/suppliers/ComparisonTable'
import { SupplierCard } from '@/components/suppliers/SupplierCard'
import { SwitchWizard } from '@/components/suppliers/SwitchWizard'
import { useSuppliers, useSupplierRecommendation, useInitiateSwitch } from '@/lib/hooks/useSuppliers'
import { useSettingsStore } from '@/lib/store/settings'
import { formatCurrency } from '@/lib/utils/format'
import {
  Grid,
  List,
  TrendingDown,
  Award,
  Leaf,
  ArrowRight,
} from 'lucide-react'
import type { Supplier, SupplierRecommendation } from '@/types'

type ViewMode = 'grid' | 'table'

export default function SuppliersPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null)
  const [showWizard, setShowWizard] = useState(false)

  const region = useSettingsStore((s) => s.region)
  const annualUsage = useSettingsStore((s) => s.annualUsageKwh)
  const currentSupplier = useSettingsStore((s) => s.currentSupplier)
  const setCurrentSupplierStore = useSettingsStore((s) => s.setCurrentSupplier)

  // Fetch data
  const { data: suppliersData, isLoading: suppliersLoading } = useSuppliers(
    region,
    annualUsage
  )
  const { data: recommendationData } = useSupplierRecommendation(
    currentSupplier?.id || '',
    annualUsage,
    region
  )

  const initiateSwitch = useInitiateSwitch()

  // Map backend supplier fields to frontend Supplier type
  const suppliers: Supplier[] = (suppliersData?.suppliers || []).map((s: any) => ({
    id: s.id,
    name: s.name,
    logo: s.logo || s.logo_url,
    avgPricePerKwh: s.avgPricePerKwh ?? (s.id === 'supplier_001' ? 0.21 : s.id === 'supplier_002' ? 0.24 : 0.22),
    standingCharge: s.standingCharge ?? 0.40,
    greenEnergy: s.greenEnergy ?? s.green_energy_provider ?? false,
    rating: s.rating ?? 0,
    estimatedAnnualCost: s.estimatedAnnualCost ?? Math.round((s.avgPricePerKwh ?? 0.22) * annualUsage + 365 * 0.40),
    tariffType: s.tariffType ?? (s.tariff_types?.[0] || 'variable'),
    exitFee: s.exitFee ?? s.exit_fee,
    contractLength: s.contractLength ?? s.contract_length,
    features: s.features ?? s.tariff_types,
  }))
  const recommendation = recommendationData?.recommendation

  // Handle supplier selection
  const handleSelectSupplier = (supplier: Supplier) => {
    setSelectedSupplier(supplier)
    setShowWizard(true)
  }

  // Handle switch completion
  const handleSwitchComplete = async () => {
    if (!selectedSupplier) return

    await initiateSwitch.mutateAsync({
      newSupplierId: selectedSupplier.id,
      gdprConsent: true,
      currentSupplierId: currentSupplier?.id,
    })

    setCurrentSupplierStore(selectedSupplier)
    setShowWizard(false)
    setSelectedSupplier(null)
  }

  // Find cheapest and greenest suppliers
  const cheapestSupplier = suppliers.length
    ? suppliers.reduce((min, s) =>
        s.estimatedAnnualCost < min.estimatedAnnualCost ? s : min
      )
    : null

  const greenestSupplier = suppliers
    .filter((s) => s.greenEnergy)
    .sort((a, b) => a.estimatedAnnualCost - b.estimatedAnnualCost)[0]

  // Wizard recommendation
  const wizardRecommendation: SupplierRecommendation | null =
    selectedSupplier && currentSupplier
      ? {
          supplier: selectedSupplier,
          currentSupplier,
          estimatedSavings:
            currentSupplier.estimatedAnnualCost -
            selectedSupplier.estimatedAnnualCost,
          paybackMonths:
            currentSupplier.exitFee
              ? Math.ceil(
                  currentSupplier.exitFee /
                    ((currentSupplier.estimatedAnnualCost -
                      selectedSupplier.estimatedAnnualCost) /
                      12)
                )
              : 0,
          confidence: 0.85,
        }
      : null

  return (
    <div className="flex flex-col">
      <Header title="Compare Suppliers" />

      <div className="p-6">
        {/* Recommendation banner */}
        {recommendation && currentSupplier && (
          <Card className="mb-6 border-success-200 bg-success-50">
            <CardContent className="p-4">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-4">
                  <Award className="h-10 w-10 text-success-600" />
                  <div>
                    <p className="font-semibold text-gray-900">
                      We found you a better deal!
                    </p>
                    <p className="text-success-700">
                      Switch to {recommendation.supplier.name} and save{' '}
                      <span className="font-bold">
                        {formatCurrency(recommendation.estimatedSavings)}
                      </span>{' '}
                      per year
                    </p>
                  </div>
                </div>
                <Button
                  variant="primary"
                  onClick={() => handleSelectSupplier(recommendation.supplier)}
                >
                  Switch Now
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats row */}
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          {/* Cheapest */}
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-success-100 p-3">
                <TrendingDown className="h-6 w-6 text-success-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Cheapest Option</p>
                <p className="font-semibold text-gray-900">
                  {cheapestSupplier?.name || '--'}
                </p>
                <p className="text-success-600">
                  {cheapestSupplier
                    ? formatCurrency(cheapestSupplier.estimatedAnnualCost)
                    : '--'}
                  /year
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Greenest */}
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-success-100 p-3">
                <Leaf className="h-6 w-6 text-success-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Greenest Option</p>
                <p className="font-semibold text-gray-900">
                  {greenestSupplier?.name || '--'}
                </p>
                <p className="text-gray-600">100% Renewable</p>
              </div>
            </CardContent>
          </Card>

          {/* Your Current */}
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-primary-100 p-3">
                <Award className="h-6 w-6 text-primary-600" />
              </div>
              <div>
                <p className="text-sm text-gray-500">Your Current</p>
                <p className="font-semibold text-gray-900">
                  {currentSupplier?.name || 'Not set'}
                </p>
                <p className="text-gray-600">
                  {currentSupplier
                    ? formatCurrency(currentSupplier.estimatedAnnualCost)
                    : '--'}
                  /year
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* View toggle and filters */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">
            {suppliers.length} Suppliers Available
          </h2>
          <div className="flex items-center gap-2">
            <Button
              variant={viewMode === 'grid' ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('grid')}
            >
              <Grid className="h-4 w-4" />
            </Button>
            <Button
              variant={viewMode === 'table' ? 'primary' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('table')}
            >
              <List className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Suppliers list */}
        {suppliersLoading ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <Skeleton key={i} variant="rectangular" height={240} />
            ))}
          </div>
        ) : viewMode === 'grid' ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {suppliers.map((supplier) => (
              <SupplierCard
                key={supplier.id}
                supplier={supplier}
                isCurrent={supplier.id === currentSupplier?.id}
                currentAnnualCost={currentSupplier?.estimatedAnnualCost}
                showDetails
                onSelect={handleSelectSupplier}
              />
            ))}
          </div>
        ) : (
          <ComparisonTable
            suppliers={suppliers}
            currentSupplierId={currentSupplier?.id}
            showFilters
            onSelect={handleSelectSupplier}
          />
        )}

        {/* Switch wizard modal */}
        {showWizard && wizardRecommendation && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6">
              <SwitchWizard
                recommendation={wizardRecommendation}
                onComplete={handleSwitchComplete}
                onCancel={() => {
                  setShowWizard(false)
                  setSelectedSupplier(null)
                }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
