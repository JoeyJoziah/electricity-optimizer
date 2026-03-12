import { PropaneDashboard } from '@/components/propane/PropaneDashboard'

export const metadata = { title: 'Propane Prices | RateShift' }

export default function PropanePage() {
  return (
    <div className="flex flex-col">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-semibold text-gray-900">Propane Prices</h1>
        <p className="text-sm text-gray-500">
          Weekly prices for Northeast states from the EIA Petroleum Survey
        </p>
      </div>
      <div className="p-6">
        <PropaneDashboard />
      </div>
    </div>
  )
}
