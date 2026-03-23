"use client";

/**
 * AuthGuard
 *
 * Client-side authentication gate for the (app) route group.
 * Renders children only when the user is authenticated.
 * Shows a loading skeleton during auth initialization, and
 * redirects to login if the user is not authenticated.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/hooks/useAuth";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { isLoading, isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const callbackUrl = encodeURIComponent(window.location.pathname);
      router.replace(`/auth/login?callbackUrl=${callbackUrl}`);
    }
  }, [isLoading, isAuthenticated, router]);

  // While auth is loading, show a minimal full-page skeleton
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-spin h-8 w-8 border-4 border-primary-500 border-t-transparent rounded-full" />
        <span className="sr-only">Loading...</span>
      </div>
    );
  }

  // If not authenticated (redirect in progress), render nothing
  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
