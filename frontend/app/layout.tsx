import type { Metadata } from "next";
import { headers } from "next/headers";
import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { AuthProvider } from "@/lib/hooks/useAuth";
import { ToastProvider } from "@/lib/contexts/toast-context";
import { ClarityScript } from "@/lib/analytics/clarity";
import { ServiceWorkerRegistrar } from "@/components/pwa/ServiceWorkerRegistrar";
import { InstallPrompt } from "@/components/pwa/InstallPrompt";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "RateShift - Save on Your Utility Bills",
    template: "%s | RateShift",
  },
  description:
    "AI-powered utility rate optimization for Americans in all 50 states. Compare electricity, gas, and more — save money with ML-powered forecasting.",
  keywords: [
    "electricity",
    "energy savings",
    "price comparison",
    "utility rates",
    "nationwide",
    "all states",
  ],
  manifest: "/manifest.json",
  openGraph: {
    title: "RateShift",
    description:
      "Save money on utilities with AI-powered optimization — all 50 states",
    type: "website",
    locale: "en_US",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "RateShift - AI-powered utility savings",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "RateShift",
    description: "AI-powered utility savings for all 50 states",
    images: ["/og-image.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <html lang="en">
      <body className={inter.className}>
        <ClarityScript nonce={nonce} />
        <ServiceWorkerRegistrar />
        <QueryProvider>
          <AuthProvider>
            <ToastProvider>
              {children}
              <InstallPrompt />
            </ToastProvider>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
