import React from 'react'
import { cn } from '@/lib/utils/cn'

interface ExtractedFieldProps {
  icon: React.ElementType
  label: string
  value: string
  highlight?: boolean
}

export function ExtractedField({
  icon: Icon,
  label,
  value,
  highlight = false,
}: ExtractedFieldProps) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border p-3',
        highlight
          ? 'border-primary-200 bg-primary-50'
          : 'border-gray-200 bg-gray-50'
      )}
    >
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
          highlight ? 'bg-primary-100' : 'bg-gray-100'
        )}
      >
        <Icon
          className={cn(
            'h-4 w-4',
            highlight ? 'text-primary-600' : 'text-gray-500'
          )}
        />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-gray-500">{label}</p>
        <p
          className={cn(
            'text-sm font-semibold truncate',
            highlight ? 'text-primary-900' : 'text-gray-900'
          )}
        >
          {value}
        </p>
      </div>
    </div>
  )
}
