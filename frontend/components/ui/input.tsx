'use client'

import React from 'react'
import { cn } from '@/lib/utils/cn'

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  labelSuffix?: React.ReactNode
  labelRight?: React.ReactNode
  error?: string
  helperText?: string
  success?: boolean
  successText?: string
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, labelSuffix, labelRight, error, helperText, success, successText, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-')

    return (
      <div className="w-full">
        {label && (
          labelRight ? (
            <div className="flex items-center justify-between mb-1.5">
              <label
                htmlFor={inputId}
                className="block text-sm font-medium text-gray-700"
              >
                {label}{labelSuffix && <span className="text-gray-400 font-normal"> {labelSuffix}</span>}
              </label>
              {labelRight}
            </div>
          ) : (
            <label
              htmlFor={inputId}
              className="mb-1.5 block text-sm font-medium text-gray-700"
            >
              {label}{labelSuffix && <span className="text-gray-400 font-normal"> {labelSuffix}</span>}
            </label>
          )
        )}
        <input
          id={inputId}
          ref={ref}
          className={cn(
            'block w-full rounded-lg border bg-white px-4 py-2.5',
            'text-gray-900 placeholder-gray-400',
            'focus:outline-none focus:ring-2 focus:ring-offset-0',
            'transition-all duration-200',
            'hover:border-gray-400',
            success && !error
              ? 'border-success-400 focus:border-success-500 focus:ring-success-500'
              : error
                ? 'border-danger-300 focus:border-danger-500 focus:ring-danger-500'
                : 'border-gray-300 focus:border-primary-500 focus:ring-primary-500',
            'disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-500',
            className
          )}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={
            error ? `${inputId}-error` :
            successText ? `${inputId}-success` :
            helperText ? `${inputId}-helper` :
            undefined
          }
          {...props}
        />
        {error && (
          <p
            id={`${inputId}-error`}
            className="mt-1.5 text-sm text-danger-600 flex items-center gap-1"
            role="alert"
          >
            <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01" />
            </svg>
            {error}
          </p>
        )}
        {successText && !error && (
          <p
            id={`${inputId}-success`}
            className="mt-1.5 text-sm text-success-600 flex items-center gap-1"
          >
            <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            {successText}
          </p>
        )}
        {helperText && !error && !successText && (
          <p id={`${inputId}-helper`} className="mt-1.5 text-sm text-gray-500">{helperText}</p>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'

export interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, label, id, ...props }, ref) => {
    const checkboxId = id || label.toLowerCase().replace(/\s+/g, '-')

    return (
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id={checkboxId}
          ref={ref}
          className={cn(
            'h-4 w-4 rounded border-gray-300',
            'text-primary-600 focus:ring-primary-500',
            'disabled:cursor-not-allowed disabled:opacity-50',
            className
          )}
          {...props}
        />
        <label
          htmlFor={checkboxId}
          className="text-sm text-gray-700 cursor-pointer"
        >
          {label}
        </label>
      </div>
    )
  }
)

Checkbox.displayName = 'Checkbox'
