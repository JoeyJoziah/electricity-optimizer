import { Sidebar } from '@/components/layout/Sidebar'
import { SidebarProvider } from '@/lib/contexts/sidebar-context'
import { FeedbackWidget } from '@/components/feedback/FeedbackWidget'

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
        <main id="main-content" className="flex-1 lg:pl-64">{children}</main>
      </div>
      <FeedbackWidget />
    </SidebarProvider>
  )
}
