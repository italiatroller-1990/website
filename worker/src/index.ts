/**
 * VitePress Translation Middleware for Cloudflare Workers
 * 
 * Dynamically translates English VitePress pages using NVIDIA Riva Translate 4B Instruct v2.
 * Caches translations to minimize API calls.
 */

// Supported language codes - keep in sync with VitePress theme/languages.ts
const SUPPORTED_LANGUAGES = new Set([
  'vi', 'es', 'fr', 'de', 'ja', 'ko', 'zh', 'pt', 'ru', 'ar', 'hi', 'th', 'id', 'ms', 'tr', 'pl', 'nl', 'sv', 'da', 'no', 'fi', 'el', 'cs', 'ro', 'hu', 'uk', 'he', 'bg', 'hr', 'sk', 'sl'
])

// Language names for system prompt - keep in sync with VitePress theme/languages.ts
const LANGUAGE_NAMES: Record<string, string> = {
  'vi': 'Vietnamese',
  'es': 'Spanish',
  'fr': 'French',
  'de': 'German',
  'ja': 'Japanese',
  'ko': 'Korean',
  'zh': 'Chinese',
  'pt': 'Portuguese',
  'ru': 'Russian',
  'ar': 'Arabic',
  'hi': 'Hindi',
  'th': 'Thai',
  'id': 'Indonesian',
  'ms': 'Malay',
  'tr': 'Turkish',
  'pl': 'Polish',
  'nl': 'Dutch',
  'sv': 'Swedish',
  'da': 'Danish',
  'no': 'Norwegian',
  'fi': 'Finnish',
  'el': 'Greek',
  'cs': 'Czech',
  'ro': 'Romanian',
  'hu': 'Hungarian',
  'uk': 'Ukrainian',
  'he': 'Hebrew',
  'bg': 'Bulgarian',
  'hr': 'Croatian',
  'sk': 'Slovak',
  'sl': 'Slovenian',
}

// System prompt for NVIDIA Riva
const SYSTEM_PROMPT_TEMPLATE = `You are a professional technical translator for a VitePress documentation website. Translate the following HTML content from English to the target language.

CRITICAL RULES:
1. Preserve ALL HTML tags, attributes, and structure exactly as they appear
2. Preserve Markdown formatting within HTML (headings, lists, code blocks, links, etc.)
3. NEVER translate URLs, link destinations, file paths, code blocks, inline code, or technical identifiers
4. NEVER translate package names, commands, API names, configuration keys, version numbers, or technical terms
5. Preserve HTML and Vue/VitePress components and their attributes
6. Preserve frontmatter keys and structure
7. Do NOT summarize, explain, expand, or omit content
8. Return ONLY the translated content with the same HTML structure
9. Maintain the author's original tone and level of formality
10. Use natural, appropriate technical terminology for the target language

Target language: {LANG}
Language name: {LANG_NAME}`

interface Env {
  TRANSLATION_CACHE: Cache
  NVIDIA_API_KEY: string
  ORIGIN: string
  MODEL: string
  CACHE_TTL_SECONDS: string
}

interface TranslationRequest {
  content: string
  lang: string
  langName: string
}

interface CachedTranslation {
  html: string
  timestamp: number
  lang: string
}

/**
 * Generate cache key from URL, language, and content hash
 */
function getCacheKey(url: string, lang: string, contentHash: string): string {
  return `translate:${lang}:${url}:${contentHash}`
}

/**
 * Generate SHA-256 hash of content for cache invalidation
 */
async function hashContent(content: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(content)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
}

/**
 * Extract main content from VitePress HTML
 * Returns the content inside the .vp-doc container
 */
function extractContent(html: string): { content: string; title: string } | null {
  try {
    // Extract title
    const titleMatch = html.match(/<title[^>]*>([^<]+)<\/title>/i)
    const title = titleMatch ? titleMatch[1].replace(/\|.*$/, '').trim() : ''

    // Extract main content area - VitePress uses .vp-doc for the main content
    // The structure is typically: <div class="vp-doc container">...content...</div>
    const contentMatch = html.match(
      /<div[^>]+class="[^"]*vp-doc[^"]*"[^>]*>([\s\S]*?)<\/div>\s*<\/div>\s*<\/div>\s*<!--\]-->/i
    )

    if (contentMatch) {
      return { content: contentMatch[1], title }
    }

    // Fallback: try to find any div with vp-doc class
    const fallbackMatch = html.match(/<div[^>]+class="[^"]*vp-doc[^"]*"[^>]*>([\s\S]*?)<\/div>/i)
    if (fallbackMatch) {
      return { content: fallbackMatch[1], title }
    }

    return null
  } catch (e) {
    console.error('Error extracting content:', e)
    return null
  }
}

/**
 * Replace content in VitePress HTML
 */
function replaceContent(html: string, newContent: string): string {
  // Replace the content inside the vp-doc div
  return html.replace(
    /(<div[^>]+class="[^"]*vp-doc[^"]*"[^>]*>)([\s\S]*?)(<\/div>\s*<\/div>\s*<\/div>\s*<!--\]-->)/i,
    `$1${newContent}$3`
  )
}

/**
 * Call NVIDIA Riva API to translate content
 */
async function translateWithRiva(
  content: string,
  lang: string,
  langName: string,
  env: Env
): Promise<string> {
  if (!env.NVIDIA_API_KEY) {
    throw new Error('NVIDIA_API_KEY is not configured')
  }

  const systemPrompt = SYSTEM_PROMPT_TEMPLATE
    .replace('{LANG}', lang)
    .replace('{LANG_NAME}', langName)

  const response = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.NVIDIA_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: env.MODEL || 'riva-translate-4b-instruct-v2',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: content },
      ],
      temperature: 0.2,
      max_tokens: 8192,
      top_p: 0.95,
    }),
  })

  if (!response.ok) {
    const errorText = await response.text()
    console.error('NVIDIA API error:', response.status, errorText)
    throw new Error(`Translation API error: ${response.status}`)
  }

  const data = await response.json() as any
  const translated = data.choices?.[0]?.message?.content

  if (!translated || typeof translated !== 'string') {
    throw new Error('Empty or invalid translation response')
  }

  return translated.trim()
}

/**
 * Main request handler
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)
    const path = url.pathname

    // Health check endpoint
    if (path === '/health') {
      return new Response(
        JSON.stringify({ status: 'ok', service: 'vitepress-translation-worker' }),
        {
          headers: { 'Content-Type': 'application/json' },
        }
      )
    }

    // Check if this is a translation request (has language prefix)
    const pathParts = path.split('/').filter(Boolean)
    if (pathParts.length === 0) {
      // No language prefix, pass through to origin
      return fetch(request)
    }

    const lang = pathParts[0]

    // Check if language is supported
    if (!SUPPORTED_LANGUAGES.has(lang)) {
      // Not a translation request, pass through
      return fetch(request)
    }

    // This is a translation request
    const restOfPath = '/' + pathParts.slice(1).join('/')
    const origin = env.ORIGIN || 'http://localhost:5173'
    const englishUrl = `${origin}${restOfPath}`

    try {
      // Fetch the English version
      const englishResponse = await fetch(englishUrl, {
        headers: {
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
      })

      if (!englishResponse.ok) {
        return new Response(
          JSON.stringify({ error: 'Page not found', path: restOfPath }),
          {
            status: englishResponse.status,
            headers: { 'Content-Type': 'application/json' },
          }
        )
      }

      const englishHtml = await englishResponse.text()
      const contentHash = await hashContent(englishHtml)

      // Check cache
      const cacheKey = getCacheKey(restOfPath, lang, contentHash)
      const cachedTranslation = await env.TRANSLATION_CACHE.match(cacheKey)

      if (cachedTranslation) {
        const translatedHtml = await cachedTranslation.text()
        return new Response(translatedHtml, {
          headers: {
            'Content-Type': 'text/html; charset=utf-8',
            'X-Translation-Cache': 'HIT',
            'X-Translation-Language': lang,
          },
        })
      }

      // Extract content
      const extracted = extractContent(englishHtml)
      if (!extracted) {
        // Fallback: return original English content
        return new Response(englishHtml, {
          headers: {
            'Content-Type': 'text/html; charset=utf-8',
            'X-Translation-Status': 'fallback',
          },
        })
      }

      // Translate
      const langName = LANGUAGE_NAMES[lang] || lang
      const translatedContent = await translateWithRiva(
        extracted.content,
        lang,
        langName,
        env
      )

      // Replace content in HTML
      const translatedHtml = replaceContent(englishHtml, translatedContent)

      // Cache the translation
      const cacheResponse = new Response(translatedHtml, {
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
        },
      })

      await env.TRANSLATION_CACHE.put(cacheKey, cacheResponse, {
        expirationTtl: parseInt(env.CACHE_TTL_SECONDS || '604800'), // 7 days default
      })

      return new Response(translatedHtml, {
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
          'X-Translation-Cache': 'MISS',
          'X-Translation-Language': lang,
        },
      })
    } catch (error) {
      console.error('Translation error:', error)

      // Fallback to English on error
      try {
        const fallbackResponse = await fetch(englishUrl)
        if (fallbackResponse.ok) {
          const fallbackHtml = await fallbackResponse.text()
          return new Response(fallbackHtml, {
            headers: {
              'Content-Type': 'text/html; charset=utf-8',
              'X-Translation-Status': 'error-fallback',
            },
          })
        }
      } catch (fallbackError) {
        console.error('Fallback error:', fallbackError)
      }

      return new Response(
        JSON.stringify({
          error: 'Translation failed',
          message: error instanceof Error ? error.message : 'Unknown error',
        }),
        {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }
      )
    }
  },
}
