'use client'

import { useEffect, useState, useCallback } from 'react'

const VISIT_COUNT_KEY = 'rateshift_visit_count'
const DISMISSED_KEY = 'rateshift_install_dismissed'
const MIN_VISITS = 2

/**
 * PWA install prompt banner.
 * Shows after the user's 2nd visit, unless dismissed.
 * Captures the beforeinstallprompt event to trigger native install.
 */
export function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<Event | null>(null)
  const [showBanner, setShowBanner] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return

    // Check if already dismissed
    if (localStorage.getItem(DISMISSED_KEY) === 'true') return

    // Increment visit counter
    const visits = parseInt(localStorage.getItem(VISIT_COUNT_KEY) || '0', 10) + 1
    localStorage.setItem(VISIT_COUNT_KEY, String(visits))

    if (visits < MIN_VISITS) return

    const handler = (e: Event) => {
      e.preventDefault()
      setDeferredPrompt(e)
      setShowBanner(true)
    }

    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  const handleInstall = useCallback(async () => {
    if (!deferredPrompt) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const prompt = deferredPrompt as any
    prompt.prompt()
    const result = await prompt.userChoice
    console.log('[PWA] Install result:', result.outcome)
    setShowBanner(false)
    setDeferredPrompt(null)
  }, [deferredPrompt])

  const handleDismiss = useCallback(() => {
    localStorage.setItem(DISMISSED_KEY, 'true')
    setShowBanner(false)
  }, [])

  if (!showBanner) return null

  return (
    <div
      role="banner"
      data-testid="install-prompt"
      className="fixed bottom-4 left-4 right-4 z-50 flex items-center justify-between rounded-lg bg-blue-600 p-4 text-white shadow-lg md:left-auto md:right-4 md:w-96"
    >
      <div className="flex-1">
        <p className="text-sm font-semibold">Install RateShift</p>
        <p className="text-xs opacity-90">Get instant access from your home screen</p>
      </div>
      <div className="ml-3 flex gap-2">
        <button
          onClick={handleDismiss}
          className="rounded px-3 py-1 text-xs opacity-80 hover:opacity-100"
          aria-label="Dismiss install prompt"
        >
          Later
        </button>
        <button
          onClick={handleInstall}
          className="rounded bg-white px-3 py-1 text-xs font-semibold text-blue-600 hover:bg-blue-50"
          aria-label="Install app"
        >
          Install
        </button>
      </div>
    </div>
  )
}
