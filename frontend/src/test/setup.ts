// Loaded before every test file (see `test.setupFiles` in vite.config.ts).
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom has no Blob.text(), which every supported browser has and the review
// import uses. Test environment only; nothing here ships in the bundle.
if (typeof Blob.prototype.text !== 'function') {
  Blob.prototype.text = function text(this: Blob) {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(reader.error)
      reader.readAsText(this)
    })
  }
}

// Vitest globals are off, so Testing Library cannot register this itself.
afterEach(() => cleanup())
