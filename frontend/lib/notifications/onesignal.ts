'use client'

import { ONESIGNAL_APP_ID } from '@/lib/config/env'

let initialized = false

export async function initOneSignal() {
  if (initialized || !ONESIGNAL_APP_ID || typeof window === 'undefined') return

  const OneSignalModule = await import('react-onesignal')
  const OneSignal = OneSignalModule.default

  await OneSignal.init({
    appId: ONESIGNAL_APP_ID,
    allowLocalhostAsSecureOrigin: process.env.NODE_ENV === 'development',
  })
  initialized = true
}

export async function requestPermission(): Promise<boolean> {
  if (typeof window === 'undefined') return false
  try {
    const OneSignalModule = await import('react-onesignal')
    await OneSignalModule.default.Slidedown.promptPush()
    return true
  } catch {
    return false
  }
}

export function isOneSignalConfigured(): boolean {
  return Boolean(ONESIGNAL_APP_ID)
}
