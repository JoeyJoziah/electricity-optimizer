import { Sidebar } from '@/components/layout/Sidebar'
import { SidebarProvider } from '@/lib/contexts/sidebar-context'
import { FeedbackWidget } from '@/components/feedback/FeedbackWidget'
import { ErrorBoundary } from '@/components/error-boundary'
import { PageErrorFallback } from '@/components/page-error-fallback'

export default function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <SidebarProvider>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-0 focus:left-0 focus:z-50 focus:p-4 focus:bg-primary-600 focus:text-white"
      >
        Skip to main content
      </a>
      <div className="flex min-h-screen">
        <Sidebar />
        <main id="main-content" className="flex-1 min-w-0 lg:pl-64">
          <ErrorBoundary fallback={<PageErrorFallback />}>
            {children}
          </ErrorBoundary>
        </main>
      </div>
      <FeedbackWidget />
    </SidebarProvider>
  )
}
