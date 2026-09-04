# VitePress Translation Worker

Cloudflare Worker that intercepts language-prefixed requests, fetches the
canonical English VitePress page from the same Worker's static assets,
translates it via NVIDIA Riva Translate 4B Instruct v2, caches the result,
and serves it to the browser.

The browser never calls NVIDIA directly.

## Architecture

```
Browser
  → /vi/about
  → Cloudflare Worker (serve_directly=false for non-asset routes)
  → strip /vi  →  canonical /about
  → ASSETS.fetch(/about)  →  English HTML
  → Translation cache
  → cache miss → NVIDIA Riva API
  → store translation
  → serve translated HTML
```

Static assets (`/assets/*`, CSS, JS, images, fonts) are served directly by
Cloudflare's asset pipeline without invoking the Worker.

## Files

```
worker/
├── src/
│   ├── index.ts        # Worker entry point
│   └── languages.ts    # Centralized language config (single source of truth)
├── wrangler.toml
├── package.json
├── tsconfig.json
├── .dev.vars.example
└── README.md
```

## Supported Languages

Vietnamese (vi), Spanish (es), French (fr), German (de), Japanese (ja), Korean (ko)

Edit `src/languages.ts` to add/remove languages. The VitePress theme file
`docs/.vitepress/theme/languages.ts` must stay in sync.

## Prerequisites

- Node.js 18+
- NVIDIA API key with Riva Translate 4B Instruct v2 access
- Cloudflare account with Workers & Assets

## Setup

```bash
cd worker
cp .dev.vars.example .dev.vars
# edit .dev.vars → set NVIDIA_API_KEY

npm install
npm run dev
```

In another terminal, run the VitePress dev server:

```bash
cd ..
npm run docs:dev
```

Then test:

```bash
curl http://localhost:8789/about
curl http://localhost:8789/vi/about
```

## Deploy

### 1. Build the VitePress site

```bash
cd ..
npm run docs:build
```

The dist output at `docs/.vitepress/dist/` is referenced by `wrangler.toml`
as the assets directory.

### 2. Set secrets

```bash
cd worker
npx wrangler secret put NVIDIA_API_KEY
# paste your API key
```

### 3. Deploy the Worker

```bash
npm run deploy
```

### 4. Bind to custom domain

In the Cloudflare dashboard:

1. **Workers & Pages** → `vitepress-translation-worker`
2. **Settings** → **Triggers** → **Domains & Routes**
3. Add custom domain: `italiatroller.dpdns.org`

Or configure a route in `wrangler.toml`:

```toml
routes = [
  { pattern = "italiatroller.dpdns.org/*" }
]
```

## How It Works

### Routing

| Request | Behaviour |
|---------|-----------|
| `/` | Serves English `index.html` from assets |
| `/about` | Serves English `about.html` from assets |
| `/assets/style.css` | Serves static asset directly |
| `/vi/` | Worker: fetches `/` → translates → caches → serves |
| `/vi/about` | Worker: fetches `/about` → translates → caches → serves |

### Content extraction

The Worker locates the `<div class="vp-doc …">` in the pre-rendered HTML
using accurate div-nesting depth tracking, extracts its inner content, and
sends only that plus the `<title>` and meta description to Riva.

HTML tags, attributes, URLs, code blocks, and technical identifiers are
preserved by the system prompt instructions.

### Caching

Translations are cached using the Cloudflare Cache API under the
`vitepress-translations` namespace. The cache key includes:

- Language code
- Canonical path
- SHA-256 hash of the English source HTML

When the VitePress site is rebuilt with different content, the hash changes
and the old cache entry is naturally bypassed.

Default TTL: 7 days (configurable via `CACHE_TTL` env var).

### Error handling

- Unsupported language prefix → served as static asset (normal 404 if missing)
- NVIDIA API failure → English page served with `X-Translation-Status: error-fallback`
- Missing API key → logged, English fallback
- NVIDIA key is **never** exposed to the browser

## Cache purge

```bash
# Purge everything
npx wrangler cache delete --namespace-name vitepress-translations
```

Or use the Cloudflare dashboard → Workers → Cache → Purge.

## Adding languages

1. Add entry to `src/languages.ts`
2. Add matching entry to `docs/.vitepress/theme/languages.ts`
3. Deploy

No code changes needed in the Worker logic.
