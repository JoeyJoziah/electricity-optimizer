'use client'

import { isDevMode } from '@/lib/utils/devGate'

export function DevBanner() {
  if (!isDevMode()) return null

  return (
    <div className="bg-amber-500 px-4 py-1.5 text-center text-sm font-medium text-white">
      Development Mode
    </div>
  )
}
