'use client'

import React, { createContext, useCallback, useContext, useState, useRef, useEffect } from 'react'
import { Toast, ToastVariant } from '@/components/ui/toast'

interface ToastItem {
  id: string
  variant: ToastVariant
  title: string
  description?: string
}

interface ToastContextValue {
  toast: (opts: {
    variant: ToastVariant
    title: string
    description?: string
    duration?: number
  }) => void
  success: (title: string, description?: string) => void
  error: (title: string, description?: string) => void
  warning: (title: string, description?: string) => void
  info: (title: string, description?: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const DEFAULT_TOAST_DURATION_MS = 5000

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const counterRef = useRef(0)
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  // Clean up all timers on unmount
  useEffect(() => {
    return () => {
      timersRef.current.forEach((timer) => clearTimeout(timer))
      timersRef.current.clear()
    }
  }, [])

  const dismiss = useCallback((id: string) => {
    const timer = timersRef.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timersRef.current.delete(id)
    }
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback(
    ({
      variant,
      title,
      description,
      duration = DEFAULT_TOAST_DURATION_MS,
    }: {
      variant: ToastVariant
      title: string
      description?: string
      duration?: number
    }) => {
      const id = `toast-${++counterRef.current}`
      setToasts((prev) => [...prev, { id, variant, title, description }])
      if (duration > 0) {
        const timer = setTimeout(() => dismiss(id), duration)
        timersRef.current.set(id, timer)
      }
    },
    [dismiss]
  )

  const success = useCallback(
    (title: string, description?: string) =>
      toast({ variant: 'success', title, description }),
    [toast]
  )
  const error = useCallback(
    (title: string, description?: string) =>
      toast({ variant: 'error', title, description }),
    [toast]
  )
  const warning = useCallback(
    (title: string, description?: string) =>
      toast({ variant: 'warning', title, description }),
    [toast]
  )
  const info = useCallback(
    (title: string, description?: string) =>
      toast({ variant: 'info', title, description }),
    [toast]
  )

  return (
    <ToastContext.Provider value={{ toast, success, error, warning, info }}>
      {children}
      <div
        aria-live="polite"
        className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
      >
        {toasts.map((t) => (
          <Toast key={t.id} {...t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
