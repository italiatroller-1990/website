/**
 * Centralized language configuration.
 * Keep in sync with docs/.vitepress/theme/languages.ts
 */
export interface LanguageConfig {
  code: string
  name: string
  nativeName: string
  abbr: string
  rivaCode: string
}

export const languages: LanguageConfig[] = [
  { code: 'vi', name: 'Vietnamese', nativeName: 'Tiếng Việt', abbr: 'VI', rivaCode: 'vi' },
  { code: 'es', name: 'Spanish', nativeName: 'Español', abbr: 'ES', rivaCode: 'es' },
  { code: 'fr', name: 'French', nativeName: 'Français', abbr: 'FR', rivaCode: 'fr' },
  { code: 'de', name: 'German', nativeName: 'Deutsch', abbr: 'DE', rivaCode: 'de' },
  { code: 'ja', name: 'Japanese', nativeName: '日本語', abbr: 'JA', rivaCode: 'ja' },
  { code: 'ko', name: 'Korean', nativeName: '한국어', abbr: 'KO', rivaCode: 'ko' },
]

const languageMap = new Map(languages.map((l) => [l.code, l]))

export function getLanguageByCode(code: string): LanguageConfig | undefined {
  return languageMap.get(code)
}

export const SUPPORTED_CODES = new Set(languages.map((l) => l.code))
