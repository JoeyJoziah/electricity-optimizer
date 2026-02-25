'use client'

import React, { useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Star, Leaf, X, Check, Zap } from 'lucide-react'
import { formatCurrency } from '@/lib/utils/format'
import type { Supplier } from '@/types'

interface SetSupplierDialogProps {
  suppliers: Supplier[]
  onSelect: (supplier: Supplier) => void
  onCancel: () => void
  isLoading?: boolean
}

export const SetSupplierDialog: React.FC<SetSupplierDialogProps> = ({
  suppliers,
  onSelect,
  onCancel,
  isLoading = false,
}) => {
  const [selected, setSelected] = useState<Supplier | null>(null)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">
            Select Your Supplier
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Choose your current electricity supplier to get personalized recommendations
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onCancel}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="max-h-[400px] space-y-2 overflow-y-auto">
        {suppliers.map((supplier) => (
          <div
            key={supplier.id}
            className={`flex cursor-pointer items-center justify-between rounded-lg border p-4 transition-colors ${
              selected?.id === supplier.id
                ? 'border-primary-500 bg-primary-50'
                : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
            }`}
            onClick={() => setSelected(supplier)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                setSelected(supplier)
              }
            }}
            role="option"
            aria-selected={selected?.id === supplier.id}
            tabIndex={0}
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
                <Zap className="h-5 w-5 text-gray-400" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{supplier.name}</p>
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <span className="flex items-center gap-1">
                    <Star className="h-3 w-3 fill-warning-400 text-warning-400" />
                    {supplier.rating}
                  </span>
                  <span>{formatCurrency(supplier.estimatedAnnualCost)}/yr</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {supplier.greenEnergy && (
                <Badge variant="success" size="sm">
                  <Leaf className="mr-1 h-3 w-3" />
                  Green
                </Badge>
              )}
              {selected?.id === supplier.id && (
                <Check className="h-5 w-5 text-primary-600" />
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex justify-end gap-3 border-t border-gray-200 pt-4">
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          variant="primary"
          disabled={!selected || isLoading}
          loading={isLoading}
          onClick={() => selected && onSelect(selected)}
        >
          <Check className="mr-2 h-4 w-4" />
          Set as My Supplier
        </Button>
      </div>
    </div>
  )
}
