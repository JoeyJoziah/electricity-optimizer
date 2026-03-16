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

    const response = await fetch(`${BACKEND_URL}/api/v1/billing/checkout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: authHeader,
      },
      body: JSON.stringify({
        tier: body.tier,
        success_url: body.success_url || `${request.nextUrl.origin}/dashboard?checkout=success`,
        cancel_url: body.cancel_url || `${request.nextUrl.origin}/pricing?checkout=cancelled`,
      }),
    })

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
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
