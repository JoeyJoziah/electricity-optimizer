'use client'

import React, { useState, useCallback } from 'react'
import { cn } from '@/lib/utils/cn'
import { formatCurrency, formatPercentage } from '@/lib/utils/format'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/input'
import {
  ArrowRight,
  ArrowLeft,
  Check,
  X,
  AlertTriangle,
  Shield,
  FileText,
  Leaf,
  Loader2,
} from 'lucide-react'
import type { SupplierRecommendation } from '@/types'

export interface SwitchWizardProps {
  recommendation: SupplierRecommendation
  onComplete?: () => Promise<void>
  onCancel?: () => void
  className?: string
}

type WizardStep = 1 | 2 | 3 | 4

const STEP_TITLES: Record<WizardStep, string> = {
  1: 'Review Recommendation',
  2: 'Data Consent',
  3: 'Contract Terms',
  4: 'Confirm Switch',
}

export const SwitchWizard: React.FC<SwitchWizardProps> = ({
  recommendation,
  onComplete,
  onCancel,
  className,
}) => {
  const [step, setStep] = useState<WizardStep>(1)
  const [gdprConsent, setGdprConsent] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { supplier, currentSupplier, estimatedSavings, paybackMonths, confidence } =
    recommendation

  const handleNext = useCallback(() => {
    if (step < 4) {
      setStep((s) => (s + 1) as WizardStep)
    }
  }, [step])

  const handleBack = useCallback(() => {
    if (step > 1) {
      setStep((s) => (s - 1) as WizardStep)
    }
  }, [step])

  const handleConfirm = useCallback(async () => {
    setIsSubmitting(true)
    setError(null)

    try {
      await onComplete?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setIsSubmitting(false)
    }
  }, [onComplete])

  const canProceed = step === 2 ? gdprConsent : true

  return (
    <div
      className={cn('', className)}
      role="region"
      aria-label="Supplier Switching Wizard"
    >
      {/* Progress indicator */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">
            Step {step} of 4
          </span>
          <span className="text-sm text-gray-500">{STEP_TITLES[step]}</span>
        </div>
        <div className="h-2 w-full rounded-full bg-gray-200">
          <div
            className="h-2 rounded-full bg-primary-600 transition-all duration-300"
            style={{ width: `${(step / 4) * 100}%` }}
          />
        </div>
      </div>

      {/* Step content */}
      <Card variant="bordered" padding="lg">
        <CardContent>
          {/* Step 1: Review Recommendation */}
          {step === 1 && (
            <div className="space-y-6">
              <h2 className="text-xl font-semibold text-gray-900">
                Review Recommendation
              </h2>

              {/* Supplier comparison */}
              <div className="grid grid-cols-2 gap-4">
                {/* Current supplier */}
                <div className="rounded-lg border border-gray-200 p-4">
                  <p className="text-sm text-gray-500 mb-2">Current Supplier</p>
                  <p className="font-semibold text-gray-900">
                    {currentSupplier.name}
                  </p>
                  <p className="text-2xl font-bold text-gray-900 mt-2">
                    {formatCurrency(currentSupplier.estimatedAnnualCost)}
                  </p>
                  <p className="text-sm text-gray-500">/year</p>
                </div>

                {/* New supplier */}
                <div className="rounded-lg border-2 border-success-500 bg-success-50 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm text-gray-500">Recommended</p>
                    {supplier.greenEnergy && (
                      <Leaf className="h-4 w-4 text-success-600" />
                    )}
                  </div>
                  <p className="font-semibold text-gray-900">{supplier.name}</p>
                  <p className="text-2xl font-bold text-success-700 mt-2">
                    {formatCurrency(supplier.estimatedAnnualCost)}
                  </p>
                  <p className="text-sm text-gray-500">/year</p>
                </div>
              </div>

              {/* Savings summary */}
              <div className="rounded-lg bg-success-100 p-4 text-center">
                <p className="text-success-800">
                  Save <span className="text-3xl font-bold">{formatCurrency(estimatedSavings)}</span> per year
                </p>
                {paybackMonths > 0 && (
                  <p className="text-sm text-success-700 mt-1">
                    Any exit fees recovered in {paybackMonths} months
                  </p>
                )}
              </div>

              {/* Confidence level */}
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-sm text-gray-600">
                  Recommendation confidence
                </span>
                <Badge variant={confidence > 0.7 ? 'success' : 'warning'}>
                  {formatPercentage(confidence * 100, 0)}
                </Badge>
              </div>
            </div>
          )}

          {/* Step 2: GDPR Consent */}
          {step === 2 && (
            <div className="space-y-6">
              <h2 className="text-xl font-semibold text-gray-900">
                Data Consent
              </h2>

              <div className="rounded-lg border border-gray-200 p-4 space-y-4">
                <div className="flex items-start gap-3">
                  <Shield className="h-6 w-6 text-primary-600 mt-0.5" />
                  <div>
                    <p className="font-medium text-gray-900">
                      Your data is protected
                    </p>
                    <p className="text-sm text-gray-600 mt-1">
                      We comply with GDPR and UK data protection laws. Your
                      information will only be shared with {supplier.name} for
                      the purpose of switching your energy supply.
                    </p>
                  </div>
                </div>

                <div className="border-t border-gray-200 pt-4">
                  <p className="text-sm text-gray-600 mb-3">
                    By checking the box below, you consent to:
                  </p>
                  <ul className="text-sm text-gray-600 space-y-2 ml-4 list-disc">
                    <li>
                      Sharing your energy usage data with {supplier.name}
                    </li>
                    <li>
                      {supplier.name} contacting you regarding the switch
                    </li>
                    <li>
                      Processing your application to become a {supplier.name}{' '}
                      customer
                    </li>
                  </ul>
                </div>
              </div>

              <div className="p-4 bg-gray-50 rounded-lg">
                <Checkbox
                  name="gdpr_consent"
                  label="I consent to the data processing described above and agree to the terms of service"
                  checked={gdprConsent}
                  onChange={(e) => setGdprConsent(e.target.checked)}
                />
              </div>
            </div>
          )}

          {/* Step 3: Contract Terms */}
          {step === 3 && (
            <div className="space-y-6">
              <h2 className="text-xl font-semibold text-gray-900">
                Contract Terms
              </h2>

              <div className="rounded-lg border border-gray-200 p-4 space-y-4">
                <div className="flex items-start gap-3">
                  <FileText className="h-6 w-6 text-primary-600 mt-0.5" />
                  <div>
                    <p className="font-medium text-gray-900">
                      Important contract information
                    </p>
                  </div>
                </div>

                {/* Exit fee warning */}
                {currentSupplier.exitFee && currentSupplier.exitFee > 0 && (
                  <div className="flex items-start gap-3 p-3 bg-warning-50 rounded-lg">
                    <AlertTriangle className="h-5 w-5 text-warning-600 mt-0.5" />
                    <div>
                      <p className="font-medium text-warning-800">Exit Fee</p>
                      <p className="text-sm text-warning-700">
                        Your current supplier may charge an exit fee of{' '}
                        <span className="font-semibold">
                          {formatCurrency(currentSupplier.exitFee)}
                        </span>
                      </p>
                    </div>
                  </div>
                )}

                {/* New contract details */}
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Tariff Type</span>
                    <span className="font-medium text-gray-900">
                      {supplier.tariffType}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Price per kWh</span>
                    <span className="font-medium text-gray-900">
                      {formatCurrency(supplier.avgPricePerKwh)}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Standing Charge</span>
                    <span className="font-medium text-gray-900">
                      {formatCurrency(supplier.standingCharge)}/day
                    </span>
                  </div>
                  {supplier.contractLength && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Contract Length</span>
                      <span className="font-medium text-gray-900">
                        {supplier.contractLength} months
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <p className="text-sm text-gray-500">
                The switch typically takes 2-3 weeks to complete. You will
                continue receiving electricity throughout the process.
              </p>
            </div>
          )}

          {/* Step 4: Confirm */}
          {step === 4 && (
            <div className="space-y-6">
              <h2 className="text-xl font-semibold text-gray-900">
                Confirm Switch
              </h2>

              <div className="rounded-lg bg-success-50 p-6 text-center">
                <Check className="h-12 w-12 text-success-600 mx-auto mb-4" />
                <p className="text-lg font-medium text-gray-900">
                  Ready to switch to {supplier.name}
                </p>
                <p className="text-success-700 mt-2">
                  Save {formatCurrency(estimatedSavings)} per year
                </p>
              </div>

              <div className="space-y-2 text-sm text-gray-600">
                <p className="flex items-center gap-2">
                  <Check className="h-4 w-4 text-success-600" />
                  Data consent provided
                </p>
                <p className="flex items-center gap-2">
                  <Check className="h-4 w-4 text-success-600" />
                  Contract terms reviewed
                </p>
              </div>

              {error && (
                <div className="p-4 bg-danger-50 rounded-lg text-danger-700">
                  <p className="font-medium">Error</p>
                  <p className="text-sm">{error}</p>
                </div>
              )}

              {isSubmitting && (
                <div className="flex items-center justify-center gap-2 text-primary-600">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>Processing your switch...</span>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Navigation buttons */}
      <div className="mt-6 flex items-center justify-between">
        <div>
          {step > 1 && (
            <Button variant="ghost" onClick={handleBack} disabled={isSubmitting}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          )}
        </div>

        <div className="flex gap-3">
          <Button variant="outline" onClick={onCancel} disabled={isSubmitting}>
            <X className="mr-2 h-4 w-4" />
            Cancel
          </Button>

          {step < 4 ? (
            <Button
              variant="primary"
              onClick={handleNext}
              disabled={!canProceed}
            >
              Next
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={handleConfirm}
              disabled={isSubmitting}
              loading={isSubmitting}
            >
              <Check className="mr-2 h-4 w-4" />
              Confirm Switch
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
