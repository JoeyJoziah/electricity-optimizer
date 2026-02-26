'use client'

import { useRouter } from 'next/navigation'
import { RegionSelector } from '@/components/onboarding/RegionSelector'
import { useUpdateProfile } from '@/lib/hooks/useProfile'
import { useSettingsStore } from '@/lib/store/settings'

export default function OnboardingPage() {
  const router = useRouter()
  const updateProfile = useUpdateProfile()

  const handleSelect = async (region: string) => {
    // Save region + mark onboarding complete in backend
    await updateProfile.mutateAsync({
      region,
      onboarding_completed: true,
    })

    // Sync to Zustand store
    useSettingsStore.getState().setRegion(region)

    // Navigate to dashboard
    window.location.href = '/dashboard'
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
      <RegionSelector onSelect={handleSelect} isLoading={updateProfile.isPending} />
    </div>
  )
}
