'use client'

import React from 'react'
import { SupplierAccountForm } from '@/components/suppliers/SupplierAccountForm'
import { useLinkAccount } from '@/lib/hooks/useSuppliers'
import { Link2 } from 'lucide-react'
import type { Supplier } from '@/types'

interface AccountLinkStepProps {
  supplier: Supplier
  onComplete: () => void
  onSkip: () => void
}

export function AccountLinkStep({ supplier, onComplete, onSkip }: AccountLinkStepProps) {
  const linkAccount = useLinkAccount()

  const handleSubmit = async (data: {
    supplierId: string
    accountNumber: string
    meterNumber?: string
    serviceZip?: string
    accountNickname?: string
    consentGiven: boolean
  }) => {
    await linkAccount.mutateAsync({
      supplier_id: data.supplierId,
      account_number: data.accountNumber,
      meter_number: data.meterNumber,
      service_zip: data.serviceZip,
      account_nickname: data.accountNickname,
      consent_given: data.consentGiven,
    })
    onComplete()
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-purple-100">
          <Link2 className="h-8 w-8 text-purple-600" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900">Link your account</h2>
        <p className="mt-2 text-gray-600">
          Connect your {supplier.name} account for automatic rate tracking
          and personalized savings insights.
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 p-4">
        <SupplierAccountForm
          supplierId={supplier.id}
          supplierName={supplier.name}
          onSubmit={handleSubmit}
          isLoading={linkAccount.isPending}
        />
      </div>

      <div className="text-center">
        <button
          type="button"
          onClick={onSkip}
          className="text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
        >
          Skip for now — I&apos;ll do this later
        </button>
        <p className="mt-2 text-xs text-gray-400">
          You can link your account any time from the Connections page.
        </p>
      </div>
    </div>
  )
}
