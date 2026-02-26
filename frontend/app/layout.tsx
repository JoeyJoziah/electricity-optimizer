import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { QueryProvider } from '@/components/providers/QueryProvider'
import { AuthProvider } from '@/lib/hooks/useAuth'
import { ToastProvider } from '@/lib/contexts/toast-context'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: {
    default: 'Electricity Optimizer - Save on CT Electricity Bills',
    template: '%s | Electricity Optimizer',
  },
  description: 'AI-powered electricity price optimization for Connecticut residents. Compare rates, get smart alerts, and save money with ML-powered forecasting.',
  keywords: ['electricity', 'Connecticut', 'energy savings', 'price comparison', 'CT electricity rates'],
  openGraph: {
    title: 'Electricity Optimizer',
    description: 'Save money on Connecticut electricity with AI-powered optimization',
    type: 'website',
    locale: 'en_US',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Electricity Optimizer',
    description: 'AI-powered electricity savings for CT residents',
  },
  robots: {
    index: true,
    follow: true,
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <QueryProvider>
          <AuthProvider>
            <ToastProvider>
              {children}
            </ToastProvider>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  )
}
