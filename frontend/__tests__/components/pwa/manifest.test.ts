import * as fs from 'fs'
import * as path from 'path'

describe('Web App Manifest', () => {
  const manifestPath = path.join(__dirname, '../../../public/manifest.json')
  let manifest: Record<string, unknown>

  beforeAll(() => {
    const raw = fs.readFileSync(manifestPath, 'utf-8')
    manifest = JSON.parse(raw)
  })

  it('is valid JSON', () => {
    expect(manifest).toBeDefined()
    expect(typeof manifest).toBe('object')
  })

  it('has required PWA fields', () => {
    expect(manifest.name).toBeTruthy()
    expect(manifest.short_name).toBeTruthy()
    expect(manifest.start_url).toBe('/')
    expect(manifest.display).toBe('standalone')
  })

  it('has theme and background colors', () => {
    expect(manifest.theme_color).toBeTruthy()
    expect(manifest.background_color).toBeTruthy()
  })

  it('has icons for 192x192 and 512x512', () => {
    const icons = manifest.icons as Array<{ sizes: string }>
    expect(icons).toBeDefined()
    expect(Array.isArray(icons)).toBe(true)

    const sizes = icons.map((i) => i.sizes)
    expect(sizes).toContain('192x192')
    expect(sizes).toContain('512x512')
  })

  it('short_name is RateShift', () => {
    expect(manifest.short_name).toBe('RateShift')
  })
})
