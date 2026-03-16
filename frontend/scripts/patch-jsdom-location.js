#!/usr/bin/env node
/**
 * Patch jsdom's Location to make properties configurable for testing.
 *
 * jsdom 26+ implements the W3C "unforgeable" spec for Location, making all
 * properties non-configurable and methods non-writable. This prevents tests
 * from mocking window.location via Object.defineProperty or direct assignment.
 *
 * This script patches the generated Location.js and Window.js to make Location
 * properties configurable, enabling standard test mocking patterns.
 *
 * Run automatically via postinstall or manually: node scripts/patch-jsdom-location.js
 */

const fs = require('fs')
const path = require('path')

const locationPath = path.resolve(
  __dirname,
  '../node_modules/jsdom/lib/jsdom/living/generated/Location.js'
)

const windowPath = path.resolve(
  __dirname,
  '../node_modules/jsdom/lib/jsdom/browser/Window.js'
)

let patchCount = 0

// Patch Location.js - make unforgeable properties configurable/writable
if (fs.existsSync(locationPath)) {
  let source = fs.readFileSync(locationPath, 'utf8')
  const marker = '/* PATCHED_FOR_JEST_30 */'

  if (!source.includes(marker)) {
    const original = source

    // Make method properties configurable and writable
    source = source.replace(
      /assign:\s*\{\s*configurable:\s*false,\s*writable:\s*false\s*\}/g,
      'assign: { configurable: true, writable: true }'
    )
    source = source.replace(
      /replace:\s*\{\s*configurable:\s*false,\s*writable:\s*false\s*\}/g,
      'replace: { configurable: true, writable: true }'
    )
    source = source.replace(
      /reload:\s*\{\s*configurable:\s*false,\s*writable:\s*false\s*\}/g,
      'reload: { configurable: true, writable: true }'
    )
    source = source.replace(
      /toString:\s*\{\s*configurable:\s*false,\s*writable:\s*false\s*\}/g,
      'toString: { configurable: true, writable: true }'
    )

    // Make getter/setter properties configurable
    const propsToFix = ['href', 'origin', 'protocol', 'host', 'hostname',
                        'port', 'pathname', 'search', 'hash']
    for (const prop of propsToFix) {
      const regex = new RegExp(`${prop}:\\s*\\{\\s*configurable:\\s*false\\s*\\}`, 'g')
      source = source.replace(regex, `${prop}: { configurable: true }`)
    }

    if (source !== original) {
      source = marker + '\n' + source
      fs.writeFileSync(locationPath, source, 'utf8')
      patchCount++
      console.log('[patch-jsdom] Patched Location.js - properties now configurable')
    } else {
      console.log('[patch-jsdom] Location.js - no changes needed')
    }
  } else {
    console.log('[patch-jsdom] Location.js - already patched')
  }
}

// Patch Window.js - make window.location configurable
if (fs.existsSync(windowPath)) {
  let source = fs.readFileSync(windowPath, 'utf8')
  const marker = '/* PATCHED_FOR_JEST_30 */'

  if (!source.includes(marker)) {
    const original = source

    source = source.replace(
      /location:\s*\{\s*configurable:\s*false\s*\}/g,
      'location: { configurable: true }'
    )

    if (source !== original) {
      source = marker + '\n' + source
      fs.writeFileSync(windowPath, source, 'utf8')
      patchCount++
      console.log('[patch-jsdom] Patched Window.js - location now configurable')
    } else {
      console.log('[patch-jsdom] Window.js - no changes needed')
    }
  } else {
    console.log('[patch-jsdom] Window.js - already patched')
  }
}

if (patchCount > 0) {
  console.log(`[patch-jsdom] Done. ${patchCount} file(s) patched.`)
} else {
  console.log('[patch-jsdom] No patches needed.')
}
