'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import { useProfile } from '@/lib/hooks/useProfile'

export default function OnboardingPage() {
  const { data: profile, isLoading } = useProfile()
  const router = useRouter()
  const redirectedRef = useRef(false)

  // Redirect completed users to dashboard (guard against double-fire)
  useEffect(() => {
    if (!isLoading && profile?.onboarding_completed && profile?.region && !redirectedRef.current) {
      redirectedRef.current = true
      router.replace('/dashboard')
    }
  }, [profile, isLoading, router])

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
