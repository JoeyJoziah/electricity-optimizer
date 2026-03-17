'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import { useProfile, useUpdateProfile } from '@/lib/hooks/useProfile'

export default function OnboardingPage() {
  const { data: profile, isLoading } = useProfile()
  const updateProfile = useUpdateProfile()
  const router = useRouter()
  const redirectedRef = useRef(false)

  // Auto-complete onboarding for users who already have a region but
  // whose onboarding_completed flag is false (data inconsistency).
  // Also redirect already-completed users to dashboard.
  useEffect(() => {
    if (isLoading || redirectedRef.current) return

    // User already has region but onboarding not marked complete — auto-fix
    if (!profile?.onboarding_completed && profile?.region) {
      redirectedRef.current = true
      updateProfile.mutateAsync({ onboarding_completed: true })
        .then(() => router.replace('/dashboard'))
        .catch(() => {
          // Don't redirect on error — let user complete wizard normally
          redirectedRef.current = false
        })
      return
    }

    // Already completed — redirect to dashboard
    if (profile?.onboarding_completed && profile?.region) {
      redirectedRef.current = true
      router.replace('/dashboard')
    }
  }, [profile, isLoading, router, updateProfile])

  const handleComplete = () => {
    if (!redirectedRef.current) {
      redirectedRef.current = true
      router.replace('/dashboard')
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-primary-600" />
      </div>
    )
  }

  // Already completed — will redirect via useEffect
  if (profile?.onboarding_completed && profile?.region) {
    return null
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
      <OnboardingWizard onComplete={handleComplete} />
    </div>
  )
}
