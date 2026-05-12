import type { Metadata } from "next";
import Link from "next/link";
import { Zap, CheckCircle } from "lucide-react";

export const metadata: Metadata = {
  title: "Unsubscribed — RateShift",
  description: "You have been unsubscribed from RateShift onboarding emails.",
};

export default function UnsubscribedPage() {
  return (
    <div className="min-h-screen bg-white">
      <nav className="border-b border-gray-100">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-2">
            <Zap className="h-8 w-8 text-blue-600" />
            <span className="text-xl font-bold text-gray-900">RateShift</span>
          </Link>
        </div>
      </nav>

      <main className="mx-auto max-w-lg px-4 py-24 sm:px-6 lg:px-8 text-center">
        <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
        <h1 className="mt-4 text-2xl font-bold text-gray-900">
          You&apos;ve been unsubscribed
        </h1>
        <p className="mt-3 text-gray-600">
          You will no longer receive onboarding emails from RateShift. Your
          account remains active — you can still log in at any time.
        </p>
        <p className="mt-6">
          <Link href="/" className="text-sm text-blue-600 hover:underline">
            Return to RateShift
          </Link>
        </p>
      </main>
    </div>
  );
}
