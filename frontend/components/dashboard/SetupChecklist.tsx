'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { useSettingsStore } from '@/lib/store/settings'
import { useUserSupplier } from '@/lib/hooks/useSuppliers'
import { CheckCircle2, Circle, ArrowRight, X, Sparkles } from 'lucide-react'
import { STATE_LABELS } from '@/lib/constants/regions'
import { cn } from '@/lib/utils/cn'

const DISMISSED_KEY = 'setup-checklist-dismissed'

interface ChecklistItem {
  id: string
  label: string
  detail?: string
  done: boolean
  href?: string
  cta?: string
}

export function SetupChecklist() {
  const [dismissed, setDismissed] = useState(true) // default to hidden until we check

  const region = useSettingsStore((s) => s.region)
  const currentSupplier = useSettingsStore((s) => s.currentSupplier)
  const { data: supplierData } = useUserSupplier()

  // Check localStorage on mount
  useEffect(() => {
    setDismissed(localStorage.getItem(DISMISSED_KEY) === 'true')
  }, [])

  const hasSupplier = !!(currentSupplier || supplierData?.supplier)

  const items: ChecklistItem[] = [
    {
      id: 'region',
      label: 'Select your state',
      detail: region ? STATE_LABELS[region] || region : undefined,
      done: !!region,
      href: '/settings',
      cta: 'Go to Settings',
    },
    {
      id: 'supplier',
      label: 'Choose your energy supplier',
      done: hasSupplier,
      href: '/suppliers',
      cta: 'Browse Suppliers',
    },
    {
      id: 'connection',
      label: 'Connect your utility account',
      done: false, // We'll assume false; connections page will show actual state
      href: '/connections',
      cta: 'Set up Connection',
    },
  ]

  const completedCount = items.filter((i) => i.done).length
  const allDone = completedCount === items.length

  // Hide if all done or dismissed
  if (allDone || dismissed) return null

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, 'true')
    setDismissed(true)
  }

  return (
    <Card className="border-primary-200 bg-gradient-to-r from-primary-50 to-blue-50" data-testid="setup-checklist">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary-600" />
            <h3 className="font-semibold text-gray-900">
              Complete your setup for personalized savings
            </h3>
          </div>
          <button
            onClick={handleDismiss}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
            aria-label="Dismiss setup checklist"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-1 mb-4">
          <p className="text-sm text-gray-500">
            {completedCount} of {items.length} complete
          </p>
          <div className="mt-2 h-1.5 w-full rounded-full bg-gray-200">
            <div
              className="h-1.5 rounded-full bg-primary-600 transition-all"
              style={{ width: `${(completedCount / items.length) * 100}%` }}
            />
          </div>
        </div>

        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.id}
              className={cn(
                'flex items-center justify-between rounded-lg px-3 py-2.5 transition-colors',
                item.done ? 'bg-white/60' : 'bg-white'
              )}
            >
              <div className="flex items-center gap-3">
                {item.done ? (
                  <CheckCircle2 className="h-5 w-5 text-success-500" />
                ) : (
                  <Circle className="h-5 w-5 text-gray-300" />
                )}
                <div>
                  <span className={cn(
                    'text-sm font-medium',
                    item.done ? 'text-gray-500 line-through' : 'text-gray-900'
                  )}>
                    {item.label}
                  </span>
                  {item.detail && (
                    <span className="ml-2 text-sm text-gray-500">({item.detail})</span>
                  )}
                </div>
              </div>
              {!item.done && item.href && (
                <Link
                  href={item.href}
                  className="flex items-center gap-1 text-sm font-medium text-primary-600 hover:text-primary-700 transition-colors"
                >
                  {item.cta}
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
