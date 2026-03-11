'use client'

import React from 'react'
import { RegionSelector } from './RegionSelector'
import { useUpdateProfile } from '@/lib/hooks/useProfile'
import { useSettingsStore } from '@/lib/store/settings'

interface OnboardingWizardProps {
  onComplete: () => void
}

/**
 * Simplified onboarding — address entry only.
 *
 * Selects region, auto-sets electricity as primary utility, completes.
 * Additional utility types are discovered post-signup via UtilityDiscoveryCard
 * on the dashboard (progressive, not front-loaded).
 */
export function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const updateProfile = useUpdateProfile()
  const settingsStore = useSettingsStore

  const handleRegionSelect = async (selectedRegion: string) => {
    // Save region + default electricity utility type
    await updateProfile.mutateAsync({
      region: selectedRegion,
      utility_types: ['electricity'],
    })
    settingsStore.getState().setRegion(selectedRegion)
    settingsStore.getState().setUtilityTypes(['electricity'])

    // Mark onboarding complete — straight to dashboard
    await updateProfile.mutateAsync({ onboarding_completed: true })
    onComplete()
  }

  return (
    <div className="mx-auto max-w-xl">
      <RegionSelector
        onSelect={handleRegionSelect}
        isLoading={updateProfile.isPending}
      />
    </div>
  )
}
