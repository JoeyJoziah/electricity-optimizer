'use client'

import React from 'react'
import Image from 'next/image'
import { cn } from '@/lib/utils/cn'
import { formatCurrency } from '@/lib/utils/format'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Star, Leaf, Zap, Check } from 'lucide-react'
import type { Supplier } from '@/types'

export interface SupplierCardProps {
  supplier: Supplier
  isCurrent?: boolean
  currentAnnualCost?: number
  showDetails?: boolean
  onSelect?: (supplier: Supplier) => void
  className?: string
}

export const SupplierCard: React.FC<SupplierCardProps> = ({
  supplier,
  isCurrent = false,
  currentAnnualCost,
  showDetails = false,
  onSelect,
  className,
}) => {
  const savings =
    currentAnnualCost && currentAnnualCost > supplier.estimatedAnnualCost
      ? currentAnnualCost - supplier.estimatedAnnualCost
      : 0

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelect?.(supplier)
    }
  }

  return (
    <Card
      className={cn(
        'transition-shadow hover:shadow-md',
        isCurrent && 'ring-2 ring-primary-500',
        className
      )}
      data-testid={`supplier-card-${supplier.id}`}
    >
      {/* Header with logo and name */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          {supplier.logo ? (
            <Image
              src={supplier.logo}
              alt={`${supplier.name} logo`}
              width={48}
              height={48}
              className="rounded-lg object-contain"
            />
          ) : (
            <div
              data-testid="supplier-logo-placeholder"
              className="flex h-12 w-12 items-center justify-center rounded-lg bg-gray-100"
            >
              <Zap className="h-6 w-6 text-gray-400" />
            </div>
          )}
          <div>
            <h3 className="font-semibold text-gray-900">{supplier.name}</h3>
            <div className="flex items-center gap-1 text-sm text-gray-500">
              <Star className="h-4 w-4 fill-warning-400 text-warning-400" />
              <span>{supplier.rating}</span>
            </div>
          </div>
        </div>

        {/* Badges */}
        <div className="flex flex-col items-end gap-1">
          {isCurrent && (
            <Badge variant="info">
              <Check className="mr-1 h-3 w-3" />
              Current Supplier
            </Badge>
          )}
          {supplier.greenEnergy && (
            <Badge variant="success">
              <Leaf className="mr-1 h-3 w-3" />
              Green Energy
            </Badge>
          )}
          <Badge variant="default">{supplier.tariffType}</Badge>
        </div>
      </div>

      {/* Pricing */}
      <div className="mt-4 grid grid-cols-2 gap-4">
        <div>
          <p className="text-sm text-gray-500">Price per kWh</p>
          <p className="text-lg font-semibold text-gray-900">
            {formatCurrency(supplier.avgPricePerKwh)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Est. Annual Cost</p>
          <p className="text-lg font-semibold text-gray-900">
            {formatCurrency(supplier.estimatedAnnualCost)}
          </p>
        </div>
      </div>

      {/* Savings indicator */}
      {savings > 0 && (
        <div className="mt-3 rounded-lg bg-success-50 p-3">
          <p className="text-center text-success-700">
            <span className="font-semibold">Save {formatCurrency(savings)}</span>
            <span className="text-sm"> per year</span>
          </p>
        </div>
      )}

      {/* Detailed info */}
      {showDetails && (
        <div className="mt-4 space-y-2 border-t border-gray-100 pt-4">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Standing Charge</span>
            <span className="font-medium text-gray-900">
              {formatCurrency(supplier.standingCharge)}/day
            </span>
          </div>

          {supplier.exitFee && (
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Exit Fee</span>
              <span className="font-medium text-danger-600">
                {formatCurrency(supplier.exitFee)}
              </span>
            </div>
          )}

          {supplier.contractLength && (
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Contract Length</span>
              <span className="font-medium text-gray-900">
                {supplier.contractLength} months
              </span>
            </div>
          )}

          {supplier.features && supplier.features.length > 0 && (
            <div className="pt-2">
              <p className="text-sm text-gray-500 mb-1">Features</p>
              <div className="flex flex-wrap gap-1">
                {supplier.features.map((feature) => (
                  <Badge key={feature} variant="default" size="sm">
                    {feature}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Action button */}
      {!isCurrent && onSelect && (
        <div className="mt-4">
          <Button
            variant="primary"
            className="w-full"
            onClick={() => onSelect(supplier)}
            onKeyDown={handleKeyDown}
          >
            Switch to {supplier.name}
          </Button>
        </div>
      )}
    </Card>
  )
}
