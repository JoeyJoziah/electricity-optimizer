'use client'

import { useState, useEffect, useRef } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useExportRates, useExportTypes } from '@/lib/hooks/useExport'

const UTILITY_LABELS: Record<string, string> = {
  electricity: 'Electricity',
  natural_gas: 'Natural Gas',
  heating_oil: 'Heating Oil',
  propane: 'Propane',
}

interface DataExportProps {
  state?: string
}

export function DataExport({ state }: DataExportProps) {
  const [selectedUtility, setSelectedUtility] = useState('electricity')
  const [format, setFormat] = useState<'json' | 'csv'>('csv')
  const [exportTriggered, setExportTriggered] = useState(false)

  const { data: types } = useExportTypes()
  const {
    data: exportData,
    isLoading,
    error,
  } = useExportRates(selectedUtility, format, state, exportTriggered)

  const handleExport = () => {
    setExportTriggered(true)
  }

  // Track whether we already triggered a download for the current data
  const downloadedRef = useRef(false)

  // Trigger CSV download when data arrives (in useEffect, not during render)
  useEffect(() => {
    if (exportData && format === 'csv' && typeof exportData.data === 'string' && !downloadedRef.current) {
      downloadedRef.current = true
      const blob = new Blob([exportData.data], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `rateshift_${selectedUtility}_rates.csv`
      a.click()
      URL.revokeObjectURL(url)
      setExportTriggered(false)
    }
  }, [exportData, format, selectedUtility])

  // Reset download guard when export is re-triggered
  useEffect(() => {
    if (exportTriggered) {
      downloadedRef.current = false
    }
  }, [exportTriggered])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Export Data</CardTitle>
        <p className="text-sm text-gray-500">
          Download historical rate data (up to 365 days, 10K rows)
        </p>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex gap-3">
            <select
              value={selectedUtility}
              onChange={(e) => {
                setSelectedUtility(e.target.value)
                setExportTriggered(false)
              }}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            >
              {(types?.supported_types || Object.keys(UTILITY_LABELS)).map(
                (type) => (
                  <option key={type} value={type}>
                    {UTILITY_LABELS[type] || type}
                  </option>
                ),
              )}
            </select>
            <select
              value={format}
              onChange={(e) => {
                setFormat(e.target.value as 'json' | 'csv')
                setExportTriggered(false)
              }}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            >
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </select>
          </div>

          <button
            onClick={handleExport}
            disabled={isLoading}
            className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {isLoading ? 'Exporting...' : 'Export Data'}
          </button>

          {error && (
            <div className="rounded-md bg-danger-50 p-3 text-sm text-danger-700">
              {error instanceof Error
                ? error.message
                : 'Failed to export data'}
            </div>
          )}

          {exportData && format === 'json' && (
            <div className="text-xs text-gray-500">
              Exported {exportData.count} rows ({exportData.date_range.start} to{' '}
              {exportData.date_range.end})
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
