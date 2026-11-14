// Which changed files the static rules read (Phase 7). Mirrors
// backend/app/pattern_rules.py: the Python heuristics read .py files, the
// pattern rules read Dart, JavaScript/TypeScript, Kotlin and Java files
// that are not test code. Used only to word the coverage notes; the backend
// decides what is analysed and reports it in `summary.pattern_rules`.
import type { Finding } from './types'

const PATTERN_EXTENSIONS = ['.dart', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.kt', '.kts', '.java']
const TEST_PATH = /(^|\/)(test|tests|__tests__|androidTest|integration_test|test_driver)\/|(_test\.dart|\.(test|spec)\.[jt]sx?|Test\.(kt|java))$/

export const PATTERN_LANGUAGES = 'Dart, JavaScript/TypeScript, Kotlin and Java'

/** True when the pattern rules read this path. */
export const isPatternFile = (path: string) =>
  PATTERN_EXTENSIONS.some(extension => path.toLowerCase().endsWith(extension)) && !TEST_PATH.test(path)

/** True when neither the Python heuristics nor the pattern rules read this path. */
export const isUnanalysed = (path: string) => !path.endsWith('.py') && !isPatternFile(path)

export const isPatternFinding = (finding: Pick<Finding, 'source'>) => finding.source === 'pattern-rules'

/** "tls-validation-disabled" from "shipsafe.tls-validation-disabled". */
export const shortRuleId = (ruleId: string | undefined) => (ruleId ?? '').replace(/^shipsafe\./, '')
