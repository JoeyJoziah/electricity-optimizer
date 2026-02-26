'use client'

import React from 'react'
import { cn } from '@/lib/utils/cn'
import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react'

export type ToastVariant = 'success' | 'error' | 'warning' | 'info'

interface ToastProps {
  id: string
  variant: ToastVariant
  title: string
  description?: string
  onDismiss: (id: string) => void
}

const VARIANT_STYLES: Record<
  ToastVariant,
  { bg: string; icon: React.ElementType; iconColor: string }
> = {
  success: {
    bg: 'bg-success-50 border-success-200',
    icon: CheckCircle,
    iconColor: 'text-success-600',
  },
  error: {
    bg: 'bg-danger-50 border-danger-200',
    icon: AlertCircle,
    iconColor: 'text-danger-600',
  },
  warning: {
    bg: 'bg-warning-50 border-warning-200',
    icon: AlertTriangle,
    iconColor: 'text-warning-600',
  },
  info: {
    bg: 'bg-blue-50 border-blue-200',
    icon: Info,
    iconColor: 'text-blue-600',
  },
}

export function Toast({ id, variant, title, description, onDismiss }: ToastProps) {
  const { bg, icon: Icon, iconColor } = VARIANT_STYLES[variant]

  return (
    <div
      role="alert"
      className={cn(
        'pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border p-4 shadow-lg',
        bg
      )}
    >
      <Icon className={cn('h-5 w-5 flex-shrink-0 mt-0.5', iconColor)} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900">{title}</p>
        {description && (
          <p className="mt-1 text-sm text-gray-600">{description}</p>
        )}
      </div>
      <button
        onClick={() => onDismiss(id)}
        className="flex-shrink-0 rounded p-1 hover:bg-gray-200/50"
        aria-label="Dismiss"
      >
        <X className="h-4 w-4 text-gray-500" />
      </button>
    </div>
  )
}
