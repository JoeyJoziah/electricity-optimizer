/**
 * Next.js Middleware — CSP Nonce + Route Protection
 *
 * 1. Generates a per-request CSP nonce and sets the Content-Security-Policy
 *    header with nonce-based script-src (no 'unsafe-inline').
 * 2. Checks for Better Auth session cookie and redirects accordingly:
 *    - Unauthenticated users accessing protected routes -> /auth/login
 *    - Authenticated users accessing auth pages -> /dashboard
 */

import { NextRequest, NextResponse } from 'next/server'

const isDev = process.env.NODE_ENV === 'development'

// Routes that require authentication
const protectedPaths = [
  '/dashboard',
  '/prices',
  '/suppliers',
  '/connections',
  '/optimize',
  '/settings',
  '/onboarding',
  '/alerts',
  '/assistant',
  '/community',
  '/water',
  '/propane',
  '/heating-oil',
  '/natural-gas',
  '/solar',
  '/forecast',
  '/analytics',
  '/gas-rates',
  '/community-solar',
  '/beta-signup',
]

// Auth routes that authenticated users should be redirected away from
const authPaths = ['/auth/login', '/auth/signup', '/auth/sign-in', '/auth/sign-up']

function buildCsp(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' https://*.clarity.ms https://cdn.onesignal.com${isDev ? " 'unsafe-eval'" : ''}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://*.rateshift.app https://*.clarity.ms",
    `font-src 'self'${isDev ? ' data:' : ''}`,
    `connect-src 'self' https://*.rateshift.app https://electricity-optimizer.onrender.com https://www.clarity.ms https://*.clarity.ms https://onesignal.com https://*.onesignal.com${isDev ? ' http://localhost:* ws://localhost:*' : ''}`,
    "worker-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Generate a per-request nonce for CSP
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64')
  const csp = buildCsp(nonce)

  // Dev-only routes: rewrite to 404 in production
  if (pathname.startsWith('/architecture') && process.env.NODE_ENV !== 'development') {
    const response = NextResponse.rewrite(new URL('/404', request.url))
    response.headers.set('Content-Security-Policy', csp)
    return response
  }

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
    const response = NextResponse.redirect(signInUrl)
    response.headers.set('Content-Security-Policy', csp)
    return response
  }

  // Redirect authenticated users away from auth pages
  if (isAuthPath && sessionToken) {
    const response = NextResponse.redirect(new URL('/dashboard', request.url))
    response.headers.set('Content-Security-Policy', csp)
    return response
  }

  // Pass nonce to server components via request header
  const requestHeaders = new Headers(request.headers)
  requestHeaders.set('x-nonce', nonce)

  const response = NextResponse.next({ request: { headers: requestHeaders } })
  response.headers.set('Content-Security-Policy', csp)

  return response
}

export const config = {
  matcher: [
    // Match all paths except static assets, images, and metadata files
    {
      source:
        '/((?!_next/static|_next/image|favicon\\.ico|sitemap\\.xml|robots\\.txt|manifest\\.json|OneSignalSDKWorker\\.js|icons/).*)',
    },
  ],
}
