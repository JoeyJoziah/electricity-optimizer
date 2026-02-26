'use client'

import React, { useState, useCallback, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { RegionSelector } from './RegionSelector'
import { UtilityTypeSelector } from './UtilityTypeSelector'
import { SupplierPicker } from './SupplierPicker'
import { AccountLinkStep } from './AccountLinkStep'
import { DEREGULATED_ELECTRICITY_STATES, ALL_STATES } from '@/lib/constants/regions'
import { useUpdateProfile } from '@/lib/hooks/useProfile'
import { useSetSupplier } from '@/lib/hooks/useSuppliers'
import { useSettingsStore } from '@/lib/store/settings'
import { ArrowLeft, Check } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import type { UtilityType } from '@/lib/store/settings'
import type { Supplier } from '@/types'

type Step = 'region' | 'utility-types' | 'supplier' | 'account-link'

interface OnboardingWizardProps {
  onComplete: () => void
}

export function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [currentStep, setCurrentStep] = useState<Step>('region')
  const [region, setRegion] = useState<string | null>(null)
  const [utilityTypes, setUtilityTypes] = useState<UtilityType[]>(['electricity'])
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null)

  const updateProfile = useUpdateProfile()
  const setSupplierMutation = useSetSupplier()
  const settingsStore = useSettingsStore

  // Determine if the selected region is deregulated
  const isDeregulated = useMemo(() => {
    if (!region) return false
    const state = ALL_STATES.find((s) => s.value === region)
    return state ? DEREGULATED_ELECTRICITY_STATES.has(state.abbr) : false
  }, [region])

  // Calculate step sequence based on deregulation status and supplier selection
  const steps = useMemo((): Step[] => {
    const base: Step[] = ['region', 'utility-types']
    if (isDeregulated) {
      base.push('supplier')
      if (selectedSupplier) {
        base.push('account-link')
      }
    }
    return base
  }, [isDeregulated, selectedSupplier])

  const currentStepIndex = steps.indexOf(currentStep)
  const isLastContentStep = currentStep === 'utility-types' && !isDeregulated
  const totalSteps = isDeregulated ? (selectedSupplier ? 4 : 3) : 2

  // Step 1: Region selected
  const handleRegionSelect = async (selectedRegion: string) => {
    setRegion(selectedRegion)
    // Save region progressively
    await updateProfile.mutateAsync({ region: selectedRegion })
    settingsStore.getState().setRegion(selectedRegion)
    setCurrentStep('utility-types')
  }

  // Step 2: Utility types confirmed
  const handleUtilityTypesNext = async () => {
    await updateProfile.mutateAsync({ utility_types: utilityTypes })
    settingsStore.getState().setUtilityTypes(utilityTypes)

    if (isDeregulated) {
      setCurrentStep('supplier')
    } else {
      // Regulated state — skip supplier, complete onboarding
      await finishOnboarding()
    }
  }

  // Step 3: Supplier selected
  const handleSupplierSelect = async (supplier: Supplier) => {
    setSelectedSupplier(supplier)
    try {
      await setSupplierMutation.mutateAsync(supplier.id)
    } catch {
      // Backend save failed — continue with local state
    }
    await updateProfile.mutateAsync({ current_supplier_id: supplier.id })
    settingsStore.getState().setCurrentSupplier(supplier)
    setCurrentStep('account-link')
  }

  // Step 3 skip: No supplier selected
  const handleSupplierSkip = async () => {
    await finishOnboarding()
  }

  // Step 4: Account linked or skipped
  const handleAccountLinkComplete = async () => {
    await finishOnboarding()
  }

  const handleAccountLinkSkip = async () => {
    await finishOnboarding()
  }

  // Mark onboarding complete
  const finishOnboarding = async () => {
    await updateProfile.mutateAsync({ onboarding_completed: true })
    onComplete()
  }

  // Navigate back
  const handleBack = useCallback(() => {
    const idx = steps.indexOf(currentStep)
    if (idx > 0) {
      setCurrentStep(steps[idx - 1])
    }
  }, [currentStep, steps])

  return (
    <div className="mx-auto max-w-xl">
      {/* Progress indicator */}
      <div className="mb-8">
        <div className="flex items-center justify-center gap-2">
          {Array.from({ length: totalSteps }).map((_, i) => (
            <div
              key={i}
              className={cn(
                'h-2 rounded-full transition-all',
                i <= currentStepIndex ? 'bg-primary-600 w-8' : 'bg-gray-200 w-2'
              )}
            />
          ))}
        </div>
        <p className="mt-3 text-center text-sm text-gray-500">
          Step {currentStepIndex + 1} of {totalSteps}
        </p>
      </div>

      {/* Back button */}
      {currentStepIndex > 0 && (
        <button
          onClick={handleBack}
          className="mb-6 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
      )}

      {/* Step content */}
      {currentStep === 'region' && (
        <RegionSelector
          onSelect={handleRegionSelect}
          isLoading={updateProfile.isPending}
        />
      )}

      {currentStep === 'utility-types' && (
        <div className="space-y-6">
          <UtilityTypeSelector
            selected={utilityTypes}
            onChange={setUtilityTypes}
          />

          {!isDeregulated && region && (
            <div className="mx-auto max-w-lg rounded-lg border border-blue-200 bg-blue-50 p-4 text-center">
              <p className="text-sm text-blue-800">
                Your state has a regulated electricity market — your utility is your
                default provider. We&apos;ll still help you optimize usage and find savings.
              </p>
            </div>
          )}

          <div className="mx-auto max-w-lg">
            <Button
              variant="primary"
              className="w-full"
              onClick={handleUtilityTypesNext}
              loading={updateProfile.isPending}
            >
              {isDeregulated ? 'Next: Choose Supplier' : 'Complete Setup'}
            </Button>
          </div>
        </div>
      )}

      {currentStep === 'supplier' && region && (
        <div className="space-y-6">
          <SupplierPicker
            region={region}
            onSelect={handleSupplierSelect}
            selectedSupplier={selectedSupplier}
          />
          <div className="mx-auto max-w-lg text-center">
            <button
              type="button"
              onClick={handleSupplierSkip}
              className="text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
            >
              Skip — I&apos;ll set this up later
            </button>
          </div>
        </div>
      )}

      {currentStep === 'account-link' && selectedSupplier && (
        <AccountLinkStep
          supplier={selectedSupplier}
          onComplete={handleAccountLinkComplete}
          onSkip={handleAccountLinkSkip}
        />
      )}
    </div>
  )
}
