'use client'

import { useEffect } from 'react'
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard'
import { useProfile } from '@/lib/hooks/useProfile'

export default function OnboardingPage() {
  const { data: profile, isLoading } = useProfile()

  // Redirect completed users to dashboard
  useEffect(() => {
    if (!isLoading && profile?.onboarding_completed && profile?.region) {
      window.location.href = '/dashboard'
    }
  }, [profile, isLoading])

  const handleComplete = () => {
    window.location.href = '/dashboard'
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
