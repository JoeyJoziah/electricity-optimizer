'use client'

import React, { useMemo, useState, useCallback } from 'react'
import { cn } from '@/lib/utils/cn'
import { formatCurrency } from '@/lib/utils/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/input'
import { Star, Leaf, ChevronUp, ChevronDown, ArrowUpDown } from 'lucide-react'
import type { Supplier } from '@/types'

export interface ComparisonTableProps {
  suppliers: Supplier[]
  currentSupplierId?: string
  showFilters?: boolean
  onSelect?: (supplier: Supplier) => void
  className?: string
}

type SortField = 'name' | 'avgPricePerKwh' | 'standingCharge' | 'estimatedAnnualCost' | 'rating'
type SortDirection = 'asc' | 'desc'

export const ComparisonTable: React.FC<ComparisonTableProps> = ({
  suppliers,
  currentSupplierId,
  showFilters = false,
  onSelect,
  className,
}) => {
  const [sortField, setSortField] = useState<SortField>('estimatedAnnualCost')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [greenEnergyOnly, setGreenEnergyOnly] = useState(false)

  // Filter suppliers
  const filteredSuppliers = useMemo(() => {
    if (!greenEnergyOnly) return suppliers
    return suppliers.filter((s) => s.greenEnergy)
  }, [suppliers, greenEnergyOnly])

  // Sort suppliers
  const sortedSuppliers = useMemo(() => {
    return [...filteredSuppliers].sort((a, b) => {
      const aValue = a[sortField]
      const bValue = b[sortField]

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        return sortDirection === 'asc'
          ? aValue.localeCompare(bValue)
          : bValue.localeCompare(aValue)
      }

      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return sortDirection === 'asc' ? aValue - bValue : bValue - aValue
      }

      return 0
    })
  }, [filteredSuppliers, sortField, sortDirection])

  // Find cheapest supplier
  const cheapestId = useMemo(() => {
    if (sortedSuppliers.length === 0) return null
    return sortedSuppliers.reduce((min, s) =>
      s.estimatedAnnualCost < min.estimatedAnnualCost ? s : min
    ).id
  }, [sortedSuppliers])

  // Get current supplier's annual cost for savings calculation
  const currentAnnualCost = useMemo(() => {
    if (!currentSupplierId) return null
    const current = suppliers.find((s) => s.id === currentSupplierId)
    return current?.estimatedAnnualCost ?? null
  }, [suppliers, currentSupplierId])

  const handleSort = useCallback((field: SortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }, [sortField])

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <ArrowUpDown className="h-4 w-4 text-gray-400" />
    }
    return sortDirection === 'asc' ? (
      <ChevronUp className="h-4 w-4 text-primary-600" />
    ) : (
      <ChevronDown className="h-4 w-4 text-primary-600" />
    )
  }

  // Empty state
  if (suppliers.length === 0) {
    return (
      <div
        className={cn(
          'flex h-48 items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50',
          className
        )}
      >
        <p className="text-gray-500">No suppliers available</p>
      </div>
    )
  }

  return (
    <div className={cn('overflow-hidden rounded-lg border border-gray-200', className)}>
      {/* Filters */}
      {showFilters && (
        <div className="border-b border-gray-200 bg-gray-50 px-4 py-3">
          <Checkbox
            label="Green Energy Only"
            checked={greenEnergyOnly}
            onChange={(e) => setGreenEnergyOnly(e.target.checked)}
          />
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full" role="table">
          <thead className="bg-gray-50">
            <tr>
              <th
                scope="col"
                className="px-4 py-3 text-left text-sm font-semibold text-gray-900"
              >
                <button
                  className="flex items-center gap-1"
                  onClick={() => handleSort('name')}
                >
                  Supplier
                  <SortIcon field="name" />
                </button>
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left text-sm font-semibold text-gray-900"
              >
                <button
                  className="flex items-center gap-1"
                  onClick={() => handleSort('avgPricePerKwh')}
                >
                  Price/kWh
                  <SortIcon field="avgPricePerKwh" />
                </button>
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left text-sm font-semibold text-gray-900"
              >
                <button
                  className="flex items-center gap-1"
                  onClick={() => handleSort('standingCharge')}
                >
                  Standing Charge
                  <SortIcon field="standingCharge" />
                </button>
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left text-sm font-semibold text-gray-900"
              >
                <button
                  className="flex items-center gap-1"
                  onClick={() => handleSort('estimatedAnnualCost')}
                >
                  Annual Cost
                  <SortIcon field="estimatedAnnualCost" />
                </button>
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left text-sm font-semibold text-gray-900"
              >
                <button
                  className="flex items-center gap-1"
                  onClick={() => handleSort('rating')}
                >
                  Rating
                  <SortIcon field="rating" />
                </button>
              </th>
              <th scope="col" className="px-4 py-3 text-right text-sm font-semibold text-gray-900">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {sortedSuppliers.map((supplier) => {
              const isCheapest = supplier.id === cheapestId
              const isCurrent = supplier.id === currentSupplierId
              const savings =
                currentAnnualCost && currentAnnualCost > supplier.estimatedAnnualCost
                  ? currentAnnualCost - supplier.estimatedAnnualCost
                  : 0

              return (
                <tr
                  key={supplier.id}
                  data-testid={`supplier-row-${supplier.id}`}
                  className={cn(
                    'hover:bg-gray-50 cursor-pointer',
                    isCheapest && 'bg-success-50',
                    isCurrent && 'bg-primary-50'
                  )}
                  onClick={() => onSelect?.(supplier)}
                >
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">
                        {supplier.name}
                      </span>
                      {supplier.greenEnergy && (
                        <span data-testid="green-badge">
                          <Leaf className="h-4 w-4 text-success-600" />
                        </span>
                      )}
                      {isCheapest && (
                        <Badge variant="success" size="sm">
                          Cheapest
                        </Badge>
                      )}
                      {isCurrent && (
                        <Badge variant="info" size="sm">
                          Current
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-4 text-gray-700">
                    {formatCurrency(supplier.avgPricePerKwh)}
                  </td>
                  <td className="px-4 py-4 text-gray-700">
                    {formatCurrency(supplier.standingCharge)}/day
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex flex-col">
                      <span className="font-medium text-gray-900">
                        {formatCurrency(supplier.estimatedAnnualCost)}
                      </span>
                      {savings > 0 && (
                        <span className="text-sm text-success-600">
                          Save {formatCurrency(savings)}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-1">
                      <Star className="h-4 w-4 fill-warning-400 text-warning-400" />
                      <span className="text-gray-700">{supplier.rating}</span>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-right">
                    {!isCurrent && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => {
                          e.stopPropagation()
                          onSelect?.(supplier)
                        }}
                      >
                        Switch
                      </Button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
