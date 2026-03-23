"use client";

import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function Error({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex h-96 items-center justify-center">
      <div className="text-center">
        <h2 className="text-lg font-semibold text-gray-900">
          Something went wrong
        </h2>
        <p className="mt-2 text-sm text-gray-500">
          We couldn&apos;t load the password reset form. Please try again.
        </p>
        <div className="mt-4 flex items-center justify-center gap-3">
          <Button onClick={reset}>Try again</Button>
          <Link
            href="/auth/login"
            className="inline-flex items-center justify-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Back to login
          </Link>
        </div>
      </div>
    </div>
  );
}
