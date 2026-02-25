'use client'

import React from 'react'
import { cn } from '@/lib/utils/cn'
import { KeyRound, Mail, Upload, ArrowRight } from 'lucide-react'

interface ConnectionMethodPickerProps {
  onSelectDirect: () => void
  onSelectEmail: () => void
  onSelectUpload: () => void
}

interface MethodOption {
  id: string
  title: string
  description: string
  icon: React.ElementType
  iconBgColor: string
  iconColor: string
  onClick: () => void
}

export function ConnectionMethodPicker({
  onSelectDirect,
  onSelectEmail,
  onSelectUpload,
}: ConnectionMethodPickerProps) {
  const methods: MethodOption[] = [
    {
      id: 'direct',
      title: 'Utility Account',
      description:
        'Connect directly to your utility provider to sync billing data automatically',
      icon: KeyRound,
      iconBgColor: 'bg-primary-100',
      iconColor: 'text-primary-600',
      onClick: onSelectDirect,
    },
    {
      id: 'email',
      title: 'Email Inbox',
      description:
        'Scan your email for utility bills and invoices to extract rate information',
      icon: Mail,
      iconBgColor: 'bg-success-100',
      iconColor: 'text-success-600',
      onClick: onSelectEmail,
    },
    {
      id: 'upload',
      title: 'Upload Bills',
      description:
        'Upload PDF or image bills and we\'ll extract your rate data',
      icon: Upload,
      iconBgColor: 'bg-warning-100',
      iconColor: 'text-warning-600',
      onClick: onSelectUpload,
    },
  ]

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {methods.map((method) => (
        <button
          key={method.id}
          onClick={method.onClick}
          className={cn(
            'group flex flex-col items-start rounded-xl border border-gray-200 bg-white p-6',
            'text-left transition-all duration-200',
            'hover:border-gray-300 hover:shadow-md',
            'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2'
          )}
        >
          <div
            className={cn(
              'flex h-12 w-12 items-center justify-center rounded-lg',
              method.iconBgColor
            )}
          >
            <method.icon className={cn('h-6 w-6', method.iconColor)} />
          </div>
          <h3 className="mt-4 text-base font-semibold text-gray-900">
            {method.title}
          </h3>
          <p className="mt-1 text-sm text-gray-500 leading-relaxed">
            {method.description}
          </p>
          <div className="mt-4 flex items-center gap-1 text-sm font-medium text-primary-600 group-hover:text-primary-700">
            Connect
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </div>
        </button>
      ))}
    </div>
  )
}
