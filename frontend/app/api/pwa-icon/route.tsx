import { ImageResponse } from 'next/og'
import { type NextRequest } from 'next/server'

const VALID_SIZES = new Set([192, 512])

export async function GET(request: NextRequest) {
  const sizeParam = request.nextUrl.searchParams.get('size')
  const size = sizeParam ? parseInt(sizeParam, 10) : 192

  if (!VALID_SIZES.has(size)) {
    return new Response('Invalid size', { status: 400 })
  }

  const strokeWidth = size >= 512 ? '1.5' : '2'
  const iconSize = Math.round(size * 0.6)
  const borderRadius = Math.round(size * 0.18)

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
          borderRadius: `${borderRadius}px`,
        }}
      >
        <svg
          width={iconSize}
          height={iconSize}
          viewBox="0 0 24 24"
          fill="none"
          stroke="white"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M13 2L3 14h9l-1 10 10-12h-9l1-10z" />
        </svg>
      </div>
    ),
    { width: size, height: size }
  )
}
