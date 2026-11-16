"use client";

import { useEffect } from "react";
import { PageErrorFallback } from "@/components/page-error-fallback";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Application error:", error);
  }, [error]);

  return <PageErrorFallback error={error} onReset={reset} />;
}
