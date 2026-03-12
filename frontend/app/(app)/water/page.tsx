import { WaterDashboard } from '@/components/water/WaterDashboard'

export const metadata = { title: 'Water Rates | RateShift' }

export default function WaterPage() {
  return (
    <div className="flex flex-col">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-semibold text-gray-900">Water Rates</h1>
        <p className="text-sm text-gray-500">
          Municipal water rate benchmarking and conservation recommendations
        </p>
      </div>
      <div className="p-6">
        <WaterDashboard />
      </div>
    </div>
  )
}
