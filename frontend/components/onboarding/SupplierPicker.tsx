'use client'

import React, { useState } from 'react'
import { SupplierSelector } from '@/components/suppliers/SupplierSelector'
import { useSuppliers } from '@/lib/hooks/useSuppliers'
import { Building2, Loader2 } from 'lucide-react'
import type { Supplier, RawSupplierRecord } from '@/types'

interface SupplierPickerProps {
  region: string
  onSelect: (supplier: Supplier) => void
  selectedSupplier: Supplier | null
}

export function SupplierPicker({ region, onSelect, selectedSupplier }: SupplierPickerProps) {
  const { data: suppliersData, isLoading } = useSuppliers(region)

  // Map backend supplier records to frontend Supplier type
  const suppliers: Supplier[] = (suppliersData?.suppliers || []).map((s: RawSupplierRecord) => ({
    id: s.id,
    name: s.name,
    logo: s.logo || s.logo_url,
    avgPricePerKwh: s.avgPricePerKwh ?? 0.22,
    standingCharge: s.standingCharge ?? 0.40,
    greenEnergy: s.greenEnergy ?? s.green_energy_provider ?? false,
    rating: s.rating ?? 0,
    estimatedAnnualCost: s.estimatedAnnualCost ?? 850,
    tariffType: (s.tariffType ?? (s.tariff_types?.[0] || 'variable')) as Supplier['tariffType'],
  }))

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
          <Building2 className="h-8 w-8 text-green-600" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900">Who is your energy supplier?</h2>
        <p className="mt-2 text-gray-600">
          Your state has a deregulated market — you can choose your supplier.
          Select your current one so we can find you better deals.
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8" role="status">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-500">Loading suppliers...</span>
        </div>
      ) : suppliers.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
          <p className="text-sm text-gray-600">
            No suppliers found for your state yet. You can skip this step
            and set your supplier later in Settings.
          </p>
        </div>
      ) : (
        <SupplierSelector
          suppliers={suppliers}
          value={selectedSupplier}
          onChange={(s) => s && onSelect(s)}
          placeholder="Search or select your current supplier..."
        />
      )}

      <p className="text-center text-xs text-gray-500">
        Not sure? Check your electricity bill for your supplier name.
        You can always change this later.
      </p>
    </div>
  )
}
