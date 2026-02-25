import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const DIAGRAMS_DIR = path.join(process.cwd(), '..', 'docs', 'architecture')

function isDev() {
  return process.env.NODE_ENV === 'development'
}

export async function GET() {
  if (!isDev()) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }

  try {
    if (!fs.existsSync(DIAGRAMS_DIR)) {
      return NextResponse.json({ diagrams: [] })
    }

    const files = fs.readdirSync(DIAGRAMS_DIR)
      .filter((f) => f.endsWith('.excalidraw'))
      .map((f) => {
        const stat = fs.statSync(path.join(DIAGRAMS_DIR, f))
        return {
          name: f.replace('.excalidraw', ''),
          updatedAt: stat.mtime.toISOString(),
        }
      })
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))

    return NextResponse.json({ diagrams: files })
  } catch {
    return NextResponse.json({ error: 'Failed to list diagrams' }, { status: 500 })
  }
}

const NAME_PATTERN = /^[a-zA-Z0-9_-]+$/

export async function POST(request: NextRequest) {
  if (!isDev()) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }

  try {
    const body = await request.json()
    const { name } = body

    if (!name || typeof name !== 'string' || !NAME_PATTERN.test(name)) {
      return NextResponse.json(
        { error: 'Invalid name. Use only letters, numbers, hyphens, and underscores.' },
        { status: 400 }
      )
    }

    const filePath = path.join(DIAGRAMS_DIR, `${name}.excalidraw`)

    if (fs.existsSync(filePath)) {
      return NextResponse.json({ error: 'Diagram already exists' }, { status: 409 })
    }

    if (!fs.existsSync(DIAGRAMS_DIR)) {
      fs.mkdirSync(DIAGRAMS_DIR, { recursive: true })
    }

    const template = {
      type: 'excalidraw',
      version: 2,
      source: 'electricity-optimizer',
      elements: [],
      appState: { gridSize: null, viewBackgroundColor: '#ffffff' },
      files: {},
    }

    fs.writeFileSync(filePath, JSON.stringify(template, null, 2))

    return NextResponse.json({ name, created: true }, { status: 201 })
  } catch {
    return NextResponse.json({ error: 'Failed to create diagram' }, { status: 500 })
  }
}
