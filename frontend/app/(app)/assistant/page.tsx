import { AgentChat } from '@/components/agent/AgentChat'

export const metadata = {
  title: 'AI Assistant — RateShift',
  description: 'Chat with RateShift AI to analyze usage, find savings, and manage alerts.',
}

export default function AssistantPage() {
  return (
    <div className="flex h-[calc(100vh-2rem)] flex-col p-4 md:p-6">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900">AI Assistant</h1>
        <p className="mt-1 text-sm text-gray-500">
          Chat with RateShift AI to find savings and optimize your electricity usage.
        </p>
      </div>
      <div className="min-h-0 flex-1">
        <AgentChat />
      </div>
    </div>
  )
}
