import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const authHeader = request.headers.get('authorization')

    if (!authHeader) {
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      )
    }

    if (!authHeader.startsWith('Bearer ')) {
      return NextResponse.json(
        { error: 'Invalid authorization format' },
        { status: 401 }
      )
    }

    if (authHeader.includes('\n') || authHeader.includes('\r')) {
      return NextResponse.json(
        { error: 'Invalid authorization header' },
        { status: 400 }
      )
    }

    // Construct redirect URLs server-side — never trust client-supplied URLs
    const origin = request.nextUrl.origin
    const successUrl = `${origin}/dashboard?checkout=success`
    const cancelUrl = `${origin}/pricing?checkout=cancelled`

    const response = await fetch(`${BACKEND_URL}/api/v1/billing/checkout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: authHeader,
      },
      body: JSON.stringify({
        tier: body.tier,
        success_url: successUrl,
        cancel_url: cancelUrl,
      }),
    })

    const data = await response.json()

    if (!response.ok) {
      // Sanitize error — only pass safe fields, never raw backend internals
      const safeError = typeof data?.detail === 'string' ? data.detail : 'Checkout failed'
      return NextResponse.json({ error: safeError }, { status: response.status })
    }

    return NextResponse.json(data)
  } catch (error) {
    console.error('Checkout error:', error)
    return NextResponse.json(
      { error: 'Failed to create checkout session' },
      { status: 500 }
    )
  }
}
