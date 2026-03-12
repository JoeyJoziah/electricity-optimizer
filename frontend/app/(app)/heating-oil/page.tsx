import { HeatingOilDashboard } from '@/components/heating-oil/HeatingOilDashboard'

export const metadata = { title: 'Heating Oil Prices | RateShift' }

export default function HeatingOilPage() {
  return (
    <div className="flex flex-col">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-semibold text-gray-900">Heating Oil Prices</h1>
        <p className="text-sm text-gray-500">
          Weekly prices for Northeast states from the EIA Petroleum Survey
        </p>
      </div>
      <div className="p-6">
        <HeatingOilDashboard />
      </div>
    </div>
  )
}
