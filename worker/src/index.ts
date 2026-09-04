/**
 * VitePress Translation Middleware for Cloudflare Workers
 *
 * Serves the static VitePress output via the ASSETS binding.
 * Intercepts requests with a language prefix, fetches the canonical
 * English page, translates it via NVIDIA Riva, caches, and serves.
 */

import { getLanguageByCode, type LanguageConfig } from './languages'

// ── Env ─────────────────────────────────────────────────────────────────────

interface Env {
  ASSETS: Fetcher
  NVIDIA_API_KEY: string
  MODEL: string
  CACHE_TTL: string
}

// ── Constants ───────────────────────────────────────────────────────────────

const RIVA_ENDPOINT = 'https://integrate.api.nvidia.com/v1/chat/completions'
const DEFAULT_MODEL = 'riva-translate-4b-instruct-v2'
const DEFAULT_CACHE_TTL = 604800 // 7 days
const CACHE_NAMESPACE = 'vitepress-translations'

const SYSTEM_PROMPT = `You are a professional technical translator for a VitePress documentation website.

Translate the content from English to the target language.

RULES:
1. The input contains two sections: [TITLE] and [HTML_CONTENT]
2. Return ONLY two sections in the same format: [TITLE] and [HTML_CONTENT]
3. Preserve ALL HTML tags, attributes, and structure exactly
4. NEVER translate URLs, link hrefs, file paths, code blocks, inline code, or technical identifiers
5. NEVER translate package names, commands, API names, config keys, version numbers, class names, or id attributes
6. Preserve all data-v-*, class, id, href, src, alt, aria-*, tabindex, and style attributes unchanged
7. Do NOT summarize, explain, expand, or omit any content
8. Maintain the original tone and level of formality
9. Use natural, appropriate technical terminology for the target language

Target language: {LANG_NAME} ({LANG_CODE})`

// ── Content extraction ──────────────────────────────────────────────────────

/**
 * Extract the inner content of the first `<div class="vp-doc …">` using
 * accurate div-nesting depth tracking. Returns the HTML *before* the
 * opening tag, the inner content, and everything from the matching
 * `</div>` onward.
 */
function extractVpDoc(
  html: string,
): { before: string; inner: string; after: string } | null {
  const marker = html.indexOf('class="vp-doc')
  if (marker === -1) return null

  // Walk back to the opening <div
  const tagStart = html.lastIndexOf('<div', marker)
  if (tagStart === -1) return null

  // End of the opening tag (past the >)
  let tagEnd = html.indexOf('>', marker)
  if (tagEnd === -1) return null
  tagEnd += 1

  // Walk forward counting div nesting
  let depth = 1
  let pos = tagEnd
  while (depth > 0 && pos < html.length) {
    const nextOpen = html.indexOf('<div', pos)
    const nextClose = html.indexOf('</div>', pos)

    if (nextClose === -1) return null // malformed

    if (nextOpen !== -1 && nextOpen < nextClose) {
      // Verify it is a real opening <div (not inside an attribute or comment)
      const ch = html.charCodeAt(nextOpen + 4)
      if (ch === 0x20 || ch === 0x3e || ch === 0x0a || ch === 0x0d || ch === 0x09) {
        depth++
      }
      pos = nextOpen + 4
    } else {
      depth--
      if (depth === 0) {
        return {
          before: html.substring(0, tagEnd),
          inner: html.substring(tagEnd, nextClose),
          after: html.substring(nextClose),
        }
      }
      pos = nextClose + 6 // '</div>'.length
    }
  }
  return null
}

/**
 * Re-assemble the full page from the extraction parts, replacing inner
 * content with a translated version.
 */
function replaceVpDocInner(
  before: string,
  inner: string,
  after: string,
): string {
  return before + inner + after
}

// ── Title extraction ────────────────────────────────────────────────────────

function extractTitle(html: string): string {
  const m = html.match(/<title[^>]*>([^<]+)<\/title>/i)
  return m ? m[1].trim() : ''
}

function replaceTitle(html: string, newTitle: string): string {
  return html.replace(
    /(<title[^>]*>)([^<]*)(<\/title>)/i,
    `$1${newTitle}$3`,
  )
}

// ── Meta description ────────────────────────────────────────────────────────

function extractMetaDescription(html: string): string {
  const m = html.match(
    /<meta\s+name="description"\s+content="([^"]*)"/i,
  )
  return m ? m[1] : ''
}

function replaceMetaDescription(html: string, newDesc: string): string {
  return html.replace(
    /(<meta\s+name="description"\s+content=")([^"]*")/i,
    `$1${newDesc}$2`,
  )
}

// ── Cache ───────────────────────────────────────────────────────────────────

async function contentHash(text: string): Promise<string> {
  const data = new TextEncoder().encode(text)
  const buf = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 16) // 16 hex chars ≈ 64 bits — enough for change detection
}

function cacheKey(
  lang: string,
  canonicalPath: string,
  hash: string,
): string {
  return `${CACHE_NAMESPACE}:${lang}:${canonicalPath}:${hash}`
}

// ── NVIDIA Riva ─────────────────────────────────────────────────────────────

interface TranslationPayload {
  title: string
  content: string
}

async function translateViaRiva(
  title: string,
  content: string,
  langConfig: LanguageConfig,
  env: Env,
): Promise<TranslationPayload> {
  const model = env.MODEL || DEFAULT_MODEL
  const systemPrompt = SYSTEM_PROMPT
    .replace('{LANG_NAME}', langConfig.name)
    .replace('{LANG_CODE}', langConfig.rivaCode)

  const userMessage =
    `[TITLE]\n${title}\n[/TITLE]\n\n[HTML_CONTENT]\n${content}\n[/HTML_CONTENT]`

  const res = await fetch(RIVA_ENDPOINT, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.NVIDIA_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userMessage },
      ],
      temperature: 0.2,
      max_tokens: 8192,
      top_p: 0.95,
    }),
  })

  if (!res.ok) {
    const err = await res.text().catch(() => '')
    throw new Error(`Riva ${res.status}: ${err.slice(0, 200)}`)
  }

  const json = (await res.json()) as any
  const raw: string = json.choices?.[0]?.message?.content ?? ''
  if (!raw) throw new Error('Empty Riva response')

  return parseTranslationResponse(raw, title, content)
}

function parseTranslationResponse(
  raw: string,
  fallbackTitle: string,
  fallbackContent: string,
): TranslationPayload {
  const titleMatch = raw.match(/\[TITLE\]\s*([\s\S]*?)\s*\[\/TITLE\]/)
  const contentMatch = raw.match(
    /\[HTML_CONTENT\]\s*([\s\S]*?)\s*\[\/HTML_CONTENT\]/,
  )

  return {
    title: titleMatch ? titleMatch[1].trim() : fallbackTitle,
    content: contentMatch ? contentMatch[1].trim() : fallbackContent,
  }
}

// ── Handler ─────────────────────────────────────────────────────────────────

async function handleTranslation(
  request: Request,
  env: Env,
  canonicalPath: string,
  langConfig: LanguageConfig,
): Promise<Response> {
  // 1. Fetch the canonical English page from assets
  const assetUrl = new URL(canonicalPath, request.url)
  // Append .html extension for cleanUrls compatibility
  // The ASSETS binding with auto-trailing-slash handles both
  // /about and /about.html, but being explicit avoids redirects.
  const assetRes = await env.ASSETS.fetch(assetUrl.href)

  if (!assetRes.ok) {
    // Page does not exist in English — pass through the 404
    return assetRes
  }

  const englishHtml = await assetRes.text()

  // 2. Check translation cache
  const hash = await contentHash(englishHtml)
  const ck = cacheKey(langConfig.code, canonicalPath, hash)

  const cache = await caches.open(CACHE_NAMESPACE)
  const cached = await cache.match(new Request(`https://cache.internal/${ck}`))
  if (cached) {
    const resp = new Response(cached.body, cached)
    resp.headers.set('X-Translation-Cache', 'HIT')
    resp.headers.set('X-Translation-Language', langConfig.code)
    return resp
  }

  // 3. Extract translatable parts
  const extracted = extractVpDoc(englishHtml)
  const title = extractTitle(englishHtml)
  const metaDesc = extractMetaDescription(englishHtml)

  // If there is nothing to translate (e.g. empty vp-doc), just serve English
  if (!extracted || (!extracted.inner.trim() && !title)) {
    return new Response(englishHtml, {
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    })
  }

  // 4. Translate
  let translated: TranslationPayload
  try {
    translated = await translateViaRiva(
      title,
      extracted.inner,
      langConfig,
      env,
    )
  } catch (err) {
    console.error(
      `[translate] ${langConfig.code} ${canonicalPath}:`,
      err instanceof Error ? err.message : err,
    )
    // Fallback: serve English
    return new Response(englishHtml, {
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'X-Translation-Status': 'error-fallback',
      },
    })
  }

  // 5. Re-assemble HTML
  let output = replaceVpDocInner(
    extracted.before,
    translated.content,
    extracted.after,
  )
  output = replaceTitle(output, translated.title)
  if (metaDesc) {
    output = replaceMetaDescription(output, translated.title)
  }

  // 6. Cache the result
  const ttl = parseInt(env.CACHE_TTL || String(DEFAULT_CACHE_TTL), 10)
  const cacheResponse = new Response(output, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': `public, max-age=${ttl}`,
    },
  })
  await cache.put(
    new Request(`https://cache.internal/${ck}`),
    cacheResponse.clone(),
  )

  // 7. Return
  const resp = new Response(output, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Translation-Cache': 'MISS',
      'X-Translation-Language': langConfig.code,
    },
  })
  return resp
}

// ── Main entry point ────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)
    const path = url.pathname

    // Health check
    if (path === '/health') {
      return Response.json({ status: 'ok', service: 'vitepress-translation' })
    }

    // Parse first path segment
    const segments = path.split('/').filter(Boolean)
    if (segments.length === 0) {
      // Root — serve English from assets
      return env.ASSETS.fetch(request)
    }

    const firstSegment = segments[0]
    const langConfig = getLanguageByCode(firstSegment)

    if (!langConfig) {
      // Not a language prefix — serve static asset
      return env.ASSETS.fetch(request)
    }

    // Build the canonical English path
    const rest = segments.slice(1)
    const canonicalPath = '/' + rest.join('/')

    return handleTranslation(request, env, canonicalPath, langConfig)
  },
}
