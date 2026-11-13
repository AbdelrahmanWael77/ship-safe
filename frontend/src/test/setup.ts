// Loaded before every test file (see `test.setupFiles` in vite.config.ts).
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest globals are off, so Testing Library cannot register this itself.
afterEach(() => cleanup())
