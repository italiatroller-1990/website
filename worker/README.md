# VitePress Translation Worker

Cloudflare Workers middleware that dynamically translates English VitePress pages using NVIDIA Riva Translate 4B Instruct v2.

## Architecture

```
Browser → Cloudflare Worker → Translation Cache → NVIDIA Riva API (on cache miss)
```

## Project Structure

```
worker/
├── src/
│   └── index.ts          # Main Worker entry point
├── wrangler.toml         # Cloudflare Workers configuration
├── package.json          # Dependencies
├── tsconfig.json         # TypeScript configuration
├── .dev.vars.example     # Environment variables template
└── README.md             # This file
```

## Features

- **Dynamic Translation**: Translates English VitePress pages on-the-fly
- **Smart Caching**: Uses Cloudflare Cache API to avoid repeated translation requests
- **Graceful Fallback**: Returns English content if translation fails
- **VitePres Compatible**: Preserves HTML structure, assets, and navigation
- **Minimal Dependencies**: No external frameworks required

## Supported Languages

Vietnamese (vi), Spanish (es), French (fr), German (de), Japanese (ja), Korean (ko), Chinese (zh), Portuguese (pt), Russian (ru), Arabic (ar), Hindi (hi), Thai (th), Indonesian (id), Malay (ms), Turkish (tr), Polish (pl), Dutch (nl), Swedish (sv), Danish (da), Norwegian (no), Finnish (fi), Greek (el), Czech (cs), Romanian (ro), Hungarian (hu), Ukrainian (uk), Hebrew (he), Bulgarian (bg), Croatian (hr), Slovak (sk), Slovenian (sl)

## Prerequisites

- [Node.js](https://nodejs.org/) (v18+)
- [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/)
- NVIDIA API key with access to Riva Translate 4B Instruct v2
- Cloudflare account with Workers access

## Local Development

1. Install dependencies:
   ```bash
   cd worker
   npm install
   ```

2. Create `.dev.vars` from the example:
   ```bash
   cp .dev.vars.example .dev.vars
   ```

3. Edit `.dev.vars` and add your NVIDIA API key:
   ```bash
   NVIDIA_API_KEY=your_actual_api_key_here
   ORIGIN=http://localhost:5173
   MODEL=riva-translate-4b-instruct-v2
   CACHE_TTL_SECONDS=604800
   ```

4. Start your VitePress site locally:
   ```bash
   cd ..
   npm run docs:dev
   ```

5. Run the Worker locally:
   ```bash
   cd worker
   npm run dev
   ```

6. Test the translation:
   ```bash
   curl http://localhost:8789/vi/about
   ```

## Cloudflare Configuration

### 1. Create a Cache Binding

```bash
cd worker
wrangler kv:namespace create TRANSLATION_CACHE
```

This will output something like:
```
{ binding = "TRANSLATION_CACHE", id = "xxx", preview_id = "yyy" }
```

Add the binding ID to `wrangler.toml`:

```toml
[[kv_namespaces]]
binding = "TRANSLATION_CACHE"
id = "your_kv_namespace_id"
preview_id = "your_preview_id"
```

### 2. Set Secrets

```bash
# Set NVIDIA API key
wrangler secret put NVIDIA_API_KEY
# Enter your API key when prompted

# Set origin (your VitePress site URL)
wrangler secret put ORIGIN
# Enter: https://italiatroller.dpdns.org

# Set model name
wrangler secret put MODEL
# Enter: riva-translate-4b-instruct-v2

# Set cache TTL
wrangler secret put CACHE_TTL_SECONDS
# Enter: 604800
```

### 3. Deploy

```bash
npm run deploy
```

### 4. Update DNS

Point your domain to the Worker:

1. In Cloudflare Dashboard, go to **Workers & Pages**
2. Select your Worker
3. Go to **Settings** → **Domains & Routes**
4. Add a custom domain or route:
   - Route: `italiatroller.dpdns.org/*`
   - Or: `italiatroller.dpdns.org/vi/*`, `italiatroller.dpdns.org/es/*`, etc.

## Cache Configuration

### Cache TTL

Default: 7 days (604800 seconds)

To change the TTL:
```bash
wrangler secret put CACHE_TTL_SECONDS
# Enter new TTL in seconds
```

### Purge Cache

To purge all translations:
```bash
npm run cache:purge
```

Or selectively via Cloudflare Dashboard → **Workers** → **Cache** → **Purge**

## Request Flow

1. **Request**: `GET /vi/about`
2. **Language Detection**: Extract `vi` from URL
3. **Fetch English**: Request `https://italiatroller.dpdns.org/about`
4. **Cache Check**: Look for cached Vietnamese translation
5. **Translate** (if cache miss):
   - Extract `.vp-doc` content from HTML
   - Send to NVIDIA Riva with system prompt
   - Receive translated HTML content
6. **Replace**: Inject translated content into VitePress layout
7. **Cache**: Store translated response
8. **Return**: Send translated HTML to browser

## Error Handling

- **Unsupported Language**: Returns 400 JSON error
- **Page Not Found**: Returns original error from origin
- **Translation Failure**: Falls back to English content with `X-Translation-Status: error-fallback` header
- **Missing API Key**: Logs error and falls back to English

## VitePress Compatibility

The Worker preserves:
- All CSS, JavaScript, images, fonts
- VitePress navigation and layout
- HTML structure and classes
- Links and assets (untouched)

Only the `.vp-doc` content area is translated.

## Adding New Languages

Edit `SUPPORTED_LANGUAGES` in `src/index.ts`:

```typescript
const SUPPORTED_LANGUAGES = new Set([
  'vi', 'es', 'fr', 'de', 'ja', 'ko', 'zh', 'pt', 'ru', 'ar',
  // Add your language code here
  'it', // Italian
])
```

## System Prompt Customization

Edit `SYSTEM_PROMPT_TEMPLATE` in `src/index.ts` to adjust translation behavior. Key rules:

- Preserve HTML structure
- Don't translate code, URLs, technical terms
- Maintain tone and formality
- Return only translated content

## Monitoring

View Worker logs:
```bash
npm run tail
```

Or in Cloudflare Dashboard → **Workers** → **Logs**.

## Security

- NVIDIA API key stored as Cloudflare secret (never committed)
- All translation happens server-side
- No client-side JavaScript injection
- No exposure of API credentials

## Troubleshooting

**Translations not working:**
1. Check `NVIDIA_API_KEY` is set: `wrangler secret list`
2. Verify origin is correct: `wrangler secret get ORIGIN`
3. Check Worker logs: `npm run tail`
4. Ensure language code is in `SUPPORTED_LANGUAGES`

**Cache not working:**
1. Verify `TRANSLATION_CACHE` binding exists in `wrangler.toml`
2. Check `X-Translation-Cache` header in responses
3. Purge cache if needed: `npm run cache:purge`

**Content not translating:**
1. Verify `.vp-doc` class exists in your VitePress HTML
2. Check that content is extractable (not empty)
3. Review NVIDIA API response in logs
