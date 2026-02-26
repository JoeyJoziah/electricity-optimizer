import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { QueryProvider } from '@/components/providers/QueryProvider'
import { AuthProvider } from '@/lib/hooks/useAuth'
import { ToastProvider } from '@/lib/contexts/toast-context'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: {
    default: 'Electricity Optimizer - Save on Your Electricity Bills',
    template: '%s | Electricity Optimizer',
  },
  description: 'AI-powered electricity price optimization for Americans in all 50 states. Compare rates, get smart alerts, and save money with ML-powered forecasting.',
  keywords: ['electricity', 'energy savings', 'price comparison', 'electricity rates', 'nationwide', 'all states'],
  openGraph: {
    title: 'Electricity Optimizer',
    description: 'Save money on electricity with AI-powered optimization — all 50 states',
    type: 'website',
    locale: 'en_US',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Electricity Optimizer',
    description: 'AI-powered electricity savings for all 50 states',
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
