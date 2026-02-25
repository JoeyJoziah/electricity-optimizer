import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const DIAGRAMS_DIR = path.join(process.cwd(), '..', 'docs', 'architecture')
const NAME_PATTERN = /^[a-zA-Z0-9_-]+$/

function isDev() {
  return process.env.NODE_ENV === 'development'
}

function sanitizeName(name: string): string | null {
  if (!name || !NAME_PATTERN.test(name)) return null
  return name
}

export async function GET(
  _request: NextRequest,
  { params }: { params: { name: string } }
) {
  if (!isDev()) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }

  const name = sanitizeName(params.name)
  if (!name) {
    return NextResponse.json({ error: 'Invalid diagram name' }, { status: 400 })
  }

  const filePath = path.join(DIAGRAMS_DIR, `${name}.excalidraw`)

  if (!fs.existsSync(filePath)) {
    return NextResponse.json({ error: 'Diagram not found' }, { status: 404 })
  }

  try {
    const content = fs.readFileSync(filePath, 'utf-8')
    const data = JSON.parse(content)
    return NextResponse.json({ name, data })
  } catch {
    return NextResponse.json({ error: 'Failed to read diagram' }, { status: 500 })
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { name: string } }
) {
  if (!isDev()) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }

  const name = sanitizeName(params.name)
  if (!name) {
    return NextResponse.json({ error: 'Invalid diagram name' }, { status: 400 })
  }

  const filePath = path.join(DIAGRAMS_DIR, `${name}.excalidraw`)

  if (!fs.existsSync(filePath)) {
    return NextResponse.json({ error: 'Diagram not found' }, { status: 404 })
  }

  try {
    const body = await request.json()
    const { data } = body

    if (!data || typeof data !== 'object') {
      return NextResponse.json({ error: 'Invalid diagram data' }, { status: 400 })
    }

    fs.writeFileSync(filePath, JSON.stringify(data, null, 2))
    return NextResponse.json({ name, saved: true })
  } catch {
    return NextResponse.json({ error: 'Failed to save diagram' }, { status: 500 })
  }
}
