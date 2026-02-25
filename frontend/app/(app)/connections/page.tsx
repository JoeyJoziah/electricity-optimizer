import { ConnectionsOverview } from '@/components/connections/ConnectionsOverview'

export const metadata = {
  title: 'Connections | Electricity Optimizer',
  description: 'Connect your utility accounts to sync rates and billing data',
}

export default function ConnectionsPage() {
  return (
    <div className="p-6 lg:p-8">
      <div className="mx-auto max-w-4xl">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Connections</h1>
          <p className="mt-1 text-sm text-gray-500">
            Sync your utility rates by connecting your provider account, email, or uploading bills.
          </p>
        </div>
        <ConnectionsOverview />
      </div>
    </div>
  )
}
