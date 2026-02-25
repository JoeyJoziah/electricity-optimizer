'use client'

import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input, Checkbox } from '@/components/ui/input'
import { Shield, HelpCircle, Link2 } from 'lucide-react'

interface SupplierAccountFormProps {
  supplierId: string
  supplierName: string
  defaultZip?: string
  onSubmit: (data: {
    supplierId: string
    accountNumber: string
    meterNumber?: string
    serviceZip?: string
    accountNickname?: string
    consentGiven: boolean
  }) => Promise<void>
  isLoading?: boolean
}

export const SupplierAccountForm: React.FC<SupplierAccountFormProps> = ({
  supplierId,
  supplierName,
  defaultZip = '',
  onSubmit,
  isLoading = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const [accountNumber, setAccountNumber] = useState('')
  const [meterNumber, setMeterNumber] = useState('')
  const [serviceZip, setServiceZip] = useState(defaultZip)
  const [nickname, setNickname] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const accountNumberValid = /^[A-Za-z0-9\-\s]{4,30}$/.test(accountNumber)
  const canSubmit = accountNumberValid && consent && !isLoading

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    try {
      await onSubmit({
        supplierId,
        accountNumber,
        meterNumber: meterNumber || undefined,
        serviceZip: serviceZip || undefined,
        accountNickname: nickname || undefined,
        consentGiven: consent,
      })
      setIsExpanded(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to link account')
    }
  }

  if (!isExpanded) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() => setIsExpanded(true)}
      >
        <Link2 className="mr-2 h-4 w-4" />
        Link Account
      </Button>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4 space-y-4 rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between">
        <h4 className="font-medium text-gray-900">
          Link Your {supplierName} Account
        </h4>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setIsExpanded(false)}
        >
          Cancel
        </Button>
      </div>

      <Input
        label="Account Number"
        value={accountNumber}
        onChange={(e) => setAccountNumber(e.target.value)}
        placeholder="e.g., 1234567890"
        required
        autoComplete="off"
        helperText={
          accountNumber && !accountNumberValid
            ? 'Must be 4-30 characters (letters, numbers, hyphens, spaces)'
            : undefined
        }
        error={accountNumber.length > 0 && !accountNumberValid}
      />

      <Input
        label="Meter Number (optional)"
        value={meterNumber}
        onChange={(e) => setMeterNumber(e.target.value)}
        placeholder="e.g., MSN-12345"
        autoComplete="off"
      />

      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Service ZIP (optional)"
          value={serviceZip}
          onChange={(e) => setServiceZip(e.target.value)}
          placeholder="e.g., 06001"
          maxLength={10}
        />
        <Input
          label="Nickname (optional)"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          placeholder="e.g., Home"
          maxLength={100}
        />
      </div>

      <div className="rounded-lg bg-gray-50 p-3">
        <div className="flex items-start gap-2">
          <Shield className="mt-0.5 h-4 w-4 text-primary-600" />
          <p className="text-xs text-gray-500">
            Your account number is encrypted with AES-256-GCM and stored securely.
            It will only be used to link your utility account. You can remove it at any time.
          </p>
        </div>
        <div className="mt-3">
          <Checkbox
            name="consent"
            label="I consent to storing my encrypted account information"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
        </div>
      </div>

      {error && (
        <p className="text-sm text-danger-600">{error}</p>
      )}

      <Button
        type="submit"
        variant="primary"
        disabled={!canSubmit}
        loading={isLoading}
        className="w-full"
      >
        Link Account
      </Button>

      <p className="text-center text-xs text-gray-400">
        <HelpCircle className="mr-1 inline h-3 w-3" />
        Find your account number on your utility bill or online portal
      </p>
    </form>
  )
}
