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

export async function loginOneSignal(userId: string): Promise<void> {
  if (!initialized || typeof window === 'undefined') return

  try {
    const OneSignalModule = await import('react-onesignal')
    await OneSignalModule.default.login(userId)
    console.log('[OneSignal] User logged in:', userId)
  } catch (err) {
    console.warn('[OneSignal] Failed to login user:', err)
  }
}

export async function logoutOneSignal(): Promise<void> {
  if (!initialized || typeof window === 'undefined') return

  try {
    const OneSignalModule = await import('react-onesignal')
    await OneSignalModule.default.logout()
    console.log('[OneSignal] User logged out')
  } catch (err) {
    console.warn('[OneSignal] Failed to logout user:', err)
  }
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
