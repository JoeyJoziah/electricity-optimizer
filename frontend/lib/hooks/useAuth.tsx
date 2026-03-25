"use client";

/**
 * Authentication Hook
 *
 * Provides authentication state and methods using Better Auth client.
 * Session management uses httpOnly cookies (no localStorage tokens).
 */

import {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
  createContext,
  useContext,
  ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { authClient } from "@/lib/auth/client";
import { getUserSupplier } from "@/lib/api/suppliers";
import { getUserProfile, updateUserProfile } from "@/lib/api/profile";
import { useSettingsStore } from "@/lib/store/settings";
import { API_URL } from "@/lib/config/env";
import { isSafeRedirect } from "@/lib/utils/url";
import { loginOneSignal, logoutOneSignal } from "@/lib/notifications/onesignal";

// Auth user type
export interface AuthUser {
  id: string;
  email: string;
  name?: string;
  emailVerified: boolean;
  createdAt: string;
}

// Auth context type
interface AuthContextType {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;
  profileFetchFailed: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name?: string) => Promise<void>;
  signOut: () => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signInWithGitHub: () => Promise<void>;
  sendMagicLink: (email: string) => Promise<void>;
  clearError: () => void;
}

// Create context
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Auth provider props
interface AuthProviderProps {
  children: ReactNode;
}

// ---------------------------------------------------------------------------
// Profile redirect helpers
//
// Extracted as pure functions so the two concerns — onboarding completion
// and region selection — are independently testable and clearly separated
// from the auth init flow.
// ---------------------------------------------------------------------------

/** App routes that require a fully-completed profile */
const PROFILE_REQUIRED_PREFIXES = [
  "/dashboard",
  "/prices",
  "/suppliers",
  "/optimize",
  "/connections",
  "/settings",
  "/alerts",
  "/assistant",
  "/community",
  "/water",
  "/propane",
  "/heating-oil",
  "/natural-gas",
  "/solar",
  "/forecast",
];

/**
 * Determine whether the current path requires a completed user profile.
 */
function isProfileRequiredPath(pathname: string): boolean {
  return PROFILE_REQUIRED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/"),
  );
}

/**
 * Check whether the user still needs to complete onboarding.
 * Returns true when `onboarding_completed` is falsy.
 */
export function checkNeedsOnboarding(profile: {
  onboarding_completed?: boolean;
}): boolean {
  return !profile.onboarding_completed;
}

/**
 * Check whether the user is missing a region selection.
 *
 * This is a separate concern from onboarding — a user may have completed
 * the wizard in a previous version that did not require region, or the
 * region could have been cleared by a profile reset.
 */
export function checkNeedsRegion(profile: { region?: string | null }): boolean {
  return !profile.region;
}

/** Delay helper for retry logic */
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Profile retry delay in milliseconds */
const PROFILE_RETRY_DELAY_MS = 1000;

/**
 * Authentication Provider
 *
 * Wraps the application and provides auth state and methods via Better Auth.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [profileFetchFailed, setProfileFetchFailed] = useState(false);
  const router = useRouter();

  // Keep a ref to the latest router so the mount-only initAuth effect always
  // uses the current router instance rather than a stale closure capture.
  // Next.js may return a new router object on navigation; without the ref
  // the effect would call replace() on the original (stale) instance.
  const routerRef = useRef(router);
  useEffect(() => {
    routerRef.current = router;
  }, [router]);

  // Ref to track whether the component is still mounted, preventing state
  // updates on unmounted components from async callbacks.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Ref to always have the latest user value available in callbacks without
  // re-creating them (avoids stale closure over `user` state).
  const userRef = useRef(user);
  useEffect(() => {
    userRef.current = user;
  }, [user]);

  // Initialize auth state from session cookie
  // Fetch session, supplier, and profile data in parallel to avoid waterfall
  // On auth pages, skip profile/supplier calls to prevent 401 redirect loops
  useEffect(() => {
    let cancelled = false;

    const initAuth = async () => {
      try {
        const pathname =
          typeof window !== "undefined" ? window.location.pathname : "/";
        const isAuthPage = pathname.startsWith("/auth/");
        const isPublicPage =
          isAuthPage ||
          pathname === "/" ||
          pathname === "/pricing" ||
          pathname === "/privacy" ||
          pathname === "/terms";

        // ------------------------------------------------------------------
        // Staggered auth initialization
        //
        // Session check first (goes to Vercel — always fast), then backend
        // calls. This avoids hitting the Render backend before we know the
        // user is even authenticated, reducing the request burst on cold
        // starts from 3 simultaneous calls to 1 + 2.
        // ------------------------------------------------------------------
        const sessionResult = await authClient.getSession().then(
          (v) => ({ status: "fulfilled" as const, value: v }),
          (e: unknown) => ({ status: "rejected" as const, reason: e }),
        );

        // Skip backend calls if session check failed or user not authenticated
        if (
          sessionResult.status !== "fulfilled" ||
          !sessionResult.value.data?.user
        ) {
          if (cancelled) return;
          setIsLoading(false);
          return;
        }

        // Backend calls fire in parallel only after session is confirmed
        const [supplierResult, profileResult] = await Promise.allSettled([
          isPublicPage
            ? Promise.resolve({ supplier: null })
            : getUserSupplier(),
          isPublicPage
            ? Promise.resolve({ region: null, onboarding_completed: false })
            : getUserProfile(),
        ]);

        if (cancelled) return;

        // Session is guaranteed fulfilled with a user at this point (early
        // return above handles the negative case).
        {
          const session = sessionResult.value.data;
          setUser({
            id: session.user.id,
            email: session.user.email,
            name: session.user.name || undefined,
            emailVerified: session.user.emailVerified,
            createdAt: session.user.createdAt?.toString() || "",
          });

          // Bind OneSignal push subscription to this user
          loginOneSignal(session.user.id);

          // Ensure the public.users profile exists for this authenticated user.
          // GET /auth/me calls ensure_user_profile on the backend, which upserts
          // the row if it is missing. This covers OAuth and magic-link sign-in
          // where signIn() is never called client-side (the redirect bypasses it).
          // Fire-and-forget: auth init must not block on this.
          fetch(`${API_URL}/auth/me`, { credentials: "include" }).catch(() => {
            /* non-fatal */
          });

          // Sync supplier if fetched successfully
          if (
            supplierResult.status === "fulfilled" &&
            supplierResult.value.supplier
          ) {
            const supplier = supplierResult.value.supplier;
            const setCurrentSupplier =
              useSettingsStore.getState().setCurrentSupplier;
            setCurrentSupplier({
              id: supplier.supplier_id,
              name: supplier.supplier_name,
              avgPricePerKwh: 0,
              standingCharge: 0,
              greenEnergy: supplier.green_energy,
              rating: supplier.rating ?? 0,
              estimatedAnnualCost: 0,
              tariffType: "variable",
            });
          }

          // ------------------------------------------------------------------
          // Profile fetch with retry
          //
          // If the initial profile fetch failed (network error, backend cold
          // start, timeout), retry once after a 1s delay before deciding
          // whether to redirect. This prevents false onboarding redirects
          // when the backend is slow to respond.
          // ------------------------------------------------------------------
          let resolvedProfile =
            profileResult.status === "fulfilled" ? profileResult.value : null;

          if (profileResult.status === "rejected" && !isPublicPage) {
            await delay(PROFILE_RETRY_DELAY_MS);
            if (cancelled) return;
            try {
              resolvedProfile = await getUserProfile();
            } catch {
              // Retry also failed — set flag and do NOT redirect based on
              // missing region since we cannot determine the true state.
              if (!cancelled) {
                setProfileFetchFailed(true);
                setIsLoading(false);
              }
              return;
            }
          }

          if (cancelled) return;

          // Sync region from profile if available.
          if (resolvedProfile && resolvedProfile.region) {
            const store = useSettingsStore.getState();
            if (!store.region) {
              store.setRegion(resolvedProfile.region);
            }
          }

          // ------------------------------------------------------------------
          // Profile completeness redirects — ONLY when fetch SUCCEEDED
          // ------------------------------------------------------------------
          if (resolvedProfile) {
            const path = window.location.pathname;

            if (isProfileRequiredPath(path)) {
              if (checkNeedsRegion(resolvedProfile)) {
                routerRef.current.replace("/onboarding");
                return;
              }

              if (checkNeedsOnboarding(resolvedProfile)) {
                updateUserProfile({ onboarding_completed: true }).catch(
                  () => {},
                );
              }
            }
          }
        }
      } catch {
        // No valid session — user is not authenticated
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    initAuth();

    return () => {
      cancelled = true;
    };
  }, []);

  // Sign in with email/password
  const signIn = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const { data, error: authError } = await authClient.signIn.email({
        email,
        password,
      });

      if (authError) {
        throw new Error(authError.message || "Failed to sign in");
      }

      if (data?.user) {
        setUser({
          id: data.user.id,
          email: data.user.email,
          name: data.user.name || undefined,
          emailVerified: data.user.emailVerified,
          createdAt: data.user.createdAt?.toString() || "",
        });

        // Bind OneSignal push subscription to this user
        loginOneSignal(data.user.id);

        // Eagerly sync the public.users profile record.
        // The backend's GET /auth/me calls ensure_user_profile, which creates
        // the record if it doesn't exist yet (ON CONFLICT DO NOTHING).
        // This is a best-effort fire-and-forget call — sign-in succeeds
        // regardless of whether the sync request completes.
        fetch(`${API_URL}/auth/me`, { credentials: "include" }).catch(() => {
          /* non-fatal */
        });
      }

      // Honor callbackUrl if the middleware set one, otherwise go to dashboard.
      // Validate via shared isSafeRedirect (blocks //evil.com, /\evil.com, javascript:, etc).
      // Read window.location at call time (not captured in closure) to get
      // the current search params.
      const params = new URLSearchParams(window.location.search);
      const callback = params.get("callbackUrl") || "/dashboard";
      const destination = isSafeRedirect(callback) ? callback : "/dashboard";

      // Full-page navigation ensures middleware evaluates with the fresh
      // session cookie (router.push uses cached prefetch that may predate
      // the cookie being set).
      window.location.href = destination;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to sign in";
      if (mountedRef.current) {
        setError(message);
      }
      throw err;
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  // Sign up with email/password
  const signUp = useCallback(
    async (email: string, password: string, name?: string) => {
      setIsLoading(true);
      setError(null);

      try {
        const { error: authError } = await authClient.signUp.email({
          email,
          password,
          name: name || "",
        });

        if (authError) {
          throw new Error(authError.message || "Failed to sign up");
        }

        // With requireEmailVerification, no session is created yet.
        // Redirect to verify-email page instead of onboarding.
        window.location.href = `/auth/verify-email?email=${encodeURIComponent(email)}`;
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to sign up";
        if (mountedRef.current) {
          setError(message);
        }
        throw err;
      } finally {
        if (mountedRef.current) {
          setIsLoading(false);
        }
      }
    },
    [],
  );

  // Sign out
  const signOut = useCallback(async () => {
    setIsLoading(true);

    // Unbind OneSignal push subscription from this user
    logoutOneSignal();

    // Invalidate backend Redis session cache first (best-effort).
    // Without this, the cached session remains valid for up to 30s
    // after Better Auth deletes it from the neon_auth.session table.
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Best-effort — frontend logout proceeds regardless
    }

    try {
      await authClient.signOut();
    } catch {
      // Swallow signOut errors — always clear local state
    } finally {
      // Clear persisted Zustand settings (region, supplier, appliances, etc.)
      // so the next user who signs in starts with a clean slate.
      useSettingsStore.getState().resetSettings();

      setUser(null);
      setProfileFetchFailed(false);
      setIsLoading(false);
      // Full-page navigation to clear all client-side state (React Query cache,
      // Zustand stores, WebSocket connections). router.push keeps stale state.
      window.location.href = "/auth/login";
    }
  }, []);

  // Sign in with Google
  const signInWithGoogle = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      await authClient.signIn.social({
        provider: "google",
        callbackURL: "/onboarding",
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to sign in with Google";
      if (mountedRef.current) {
        setError(message);
      }
      throw err;
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  // Sign in with GitHub
  const signInWithGitHub = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      await authClient.signIn.social({
        provider: "github",
        callbackURL: "/onboarding",
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to sign in with GitHub";
      if (mountedRef.current) {
        setError(message);
      }
      throw err;
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  // Send magic link via Better Auth magic-link plugin
  const sendMagicLink = useCallback(async (email: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const { error: authError } = await authClient.signIn.magicLink({
        email,
        callbackURL: "/dashboard",
      });

      if (authError) {
        throw new Error(authError.message || "Failed to send magic link");
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to send magic link";
      if (mountedRef.current) {
        setError(message);
      }
      throw err;
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const value = useMemo<AuthContextType>(
    () => ({
      user,
      isLoading,
      isAuthenticated: !!user,
      error,
      profileFetchFailed,
      signIn,
      signUp,
      signOut,
      signInWithGoogle,
      signInWithGitHub,
      sendMagicLink,
      clearError,
    }),
    [
      user,
      isLoading,
      error,
      profileFetchFailed,
      signIn,
      signUp,
      signOut,
      signInWithGoogle,
      signInWithGitHub,
      sendMagicLink,
      clearError,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Hook to use authentication
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}

/**
 * Hook to require authentication
 *
 * Redirects to login if not authenticated.
 */
export function useRequireAuth(): AuthContextType {
  const auth = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      router.push("/auth/login");
    }
  }, [auth.isLoading, auth.isAuthenticated, router]);

  return auth;
}
