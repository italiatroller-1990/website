export const languages = [
  { code: "en", name: "English", nativeName: "English", abbr: "EN" },
  { code: "vi", name: "Vietnamese", nativeName: "Tiếng Việt", abbr: "VI" },
  { code: "es", name: "Spanish", nativeName: "Español", abbr: "ES" },
  { code: "fr", name: "French", nativeName: "Français", abbr: "FR" },
  { code: "de", name: "German", nativeName: "Deutsch", abbr: "DE" },
  { code: "ja", name: "Japanese", nativeName: "日本語", abbr: "JA" },
  { code: "ko", name: "Korean", nativeName: "한국어", abbr: "KO" },
] as const

export type Language = typeof languages[number]
