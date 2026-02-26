'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import { Zap, Flame, Droplets, Sun, Users } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import type { UtilityType } from '@/lib/store/settings'

interface UtilityTypeSelectorProps {
  selected: UtilityType[]
  onChange: (types: UtilityType[]) => void
}

const UTILITY_OPTIONS: { type: UtilityType; label: string; icon: React.ElementType; description: string }[] = [
  { type: 'electricity', label: 'Electricity', icon: Zap, description: 'Electric power for your home' },
  { type: 'natural_gas', label: 'Natural Gas', icon: Flame, description: 'Gas for heating and cooking' },
  { type: 'heating_oil', label: 'Heating Oil', icon: Droplets, description: 'Oil-based home heating' },
  { type: 'propane', label: 'Propane', icon: Flame, description: 'Propane gas delivery' },
  { type: 'community_solar', label: 'Community Solar', icon: Sun, description: 'Shared solar energy credits' },
]

export function UtilityTypeSelector({ selected, onChange }: UtilityTypeSelectorProps) {
  const toggle = (type: UtilityType) => {
    if (selected.includes(type)) {
      // Don't allow deselecting the last one
      if (selected.length > 1) {
        onChange(selected.filter((t) => t !== type))
      }
    } else {
      onChange([...selected, type])
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-amber-100">
          <Zap className="h-8 w-8 text-amber-600" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900">What utilities do you use?</h2>
        <p className="mt-2 text-gray-600">
          Select all that apply. We&apos;ll track rates and find savings for each.
        </p>
      </div>

      <div className="space-y-3">
        {UTILITY_OPTIONS.map(({ type, label, icon: Icon, description }) => {
          const isSelected = selected.includes(type)
          return (
            <button
              key={type}
              type="button"
              onClick={() => toggle(type)}
              className={cn(
                'flex w-full items-center gap-4 rounded-lg border-2 p-4 text-left transition-all',
                isSelected
                  ? 'border-primary-500 bg-primary-50 ring-1 ring-primary-500'
                  : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
              )}
            >
              <div className={cn(
                'flex h-10 w-10 items-center justify-center rounded-lg',
                isSelected ? 'bg-primary-100' : 'bg-gray-100'
              )}>
                <Icon className={cn(
                  'h-5 w-5',
                  isSelected ? 'text-primary-600' : 'text-gray-500'
                )} />
              </div>
              <div className="flex-1">
                <p className={cn(
                  'font-medium',
                  isSelected ? 'text-primary-900' : 'text-gray-900'
                )}>{label}</p>
                <p className="text-sm text-gray-500">{description}</p>
              </div>
              <div className={cn(
                'flex h-6 w-6 items-center justify-center rounded-full border-2 transition-colors',
                isSelected
                  ? 'border-primary-500 bg-primary-500'
                  : 'border-gray-300'
              )}>
                {isSelected && (
                  <svg className="h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>
            </button>
          )
        })}
      </div>

      <p className="text-center text-xs text-gray-500">
        Electricity is selected by default. You can change this later in Settings.
      </p>
    </div>
  )
}
