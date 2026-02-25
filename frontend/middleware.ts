/**
 * Next.js Middleware — Route Protection
 *
 * Checks for Better Auth session cookie and redirects accordingly:
 * - Unauthenticated users accessing protected routes → /auth/login
 * - Authenticated users accessing auth pages → /dashboard
 */

import { NextRequest, NextResponse } from 'next/server'

// Routes that require authentication
const protectedPaths = ['/dashboard', '/prices', '/suppliers', '/optimize', '/settings']

// Auth routes that authenticated users should be redirected away from
const authPaths = ['/auth/login', '/auth/signup', '/auth/sign-in', '/auth/sign-up']

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Better Auth sets a session token cookie.
  // On HTTPS (production), the cookie is prefixed with __Secure- automatically.
  const sessionToken =
    request.cookies.get('better-auth.session_token')?.value ||
    request.cookies.get('__Secure-better-auth.session_token')?.value

  const isProtectedPath = protectedPaths.some(
    (path) => pathname === path || pathname.startsWith(path + '/')
  )
  const isAuthPath = authPaths.some(
    (path) => pathname === path || pathname.startsWith(path + '/')
  )

  // Redirect unauthenticated users away from protected routes
  if (isProtectedPath && !sessionToken) {
    const signInUrl = new URL('/auth/login', request.url)
    signInUrl.searchParams.set('callbackUrl', pathname)
    return NextResponse.redirect(signInUrl)
  }

  // Redirect authenticated users away from auth pages
  if (isAuthPath && sessionToken) {
    return NextResponse.redirect(new URL('/dashboard', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/dashboard/:path*',
    '/prices/:path*',
    '/suppliers/:path*',
    '/optimize/:path*',
    '/settings/:path*',
    '/auth/:path*',
  ],
}
