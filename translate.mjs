#!/usr/bin/env node
/**
 * VitePress Markdown Translator
 * ==============================
 *
 * Translates English Markdown source files in docs/ to target languages
 * using an OpenAI-compatible API (NVIDIA NIM).
 *
 * Features:
 * - Translates Markdown source, not generated HTML
 * - Content-hash cache survives between builds
 * - Page-level incremental detection (skip unchanged pages)
 * - Placeholder-based syntax protection (code, HTML, URLs, VitePress)
 * - Parallel API requests with configurable workers
 * - Atomic writes for cache and translated files
 * - Strict validation of translated output
 *
 * Usage:
 *   node translate.mjs
 *   node translate.mjs --langs vi,ja
 *   node translate.mjs --workers 2
 *   node translate.mjs --dry-run
 *   node translate.mjs --clear-cache
 *   node translate.mjs --force
 *   node translate.mjs --strict
 */

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, unlinkSync, writeFileSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve, relative, sep } from "node:path";
import { parseArgs } from "node:util";

// ============================================================
// CONFIGURATION
// ============================================================

const DOCS_DIR = join(process.cwd(), "docs");
const CACHE_FILE = join(DOCS_DIR, ".vitepress", "translation-cache.json");
const STATE_FILE = join(DOCS_DIR, ".vitepress", "translation-state.json");

const API_KEY = (process.env.TRANSLATION_API_KEY || process.env.NVIDIA_API_KEY || "").trim();
const BASE_URL = process.env.TRANSLATION_BASE_URL || "https://integrate.api.nvidia.com/v1";
const MODEL = process.env.TRANSLATION_MODEL || "openai/gpt-oss-20b";
const WORKERS = parseInt(process.env.TRANSLATION_WORKERS || "2", 10);
const TIMEOUT = parseInt(process.env.TRANSLATION_TIMEOUT || "120", 10) * 1000;
const MAX_RETRIES = parseInt(process.env.TRANSLATION_MAX_RETRIES || "5", 10);
const RETRY_DELAYS = [2, 4, 8, 16, 32];

const CACHE_VERSION = 7;
const REQUEST_DELAY = 1500; // ms between requests (NVIDIA NIM 40 RPM)
const MAX_TOKENS = 32768;
const MIN_TEXT_LENGTH = 2;
const MIN_CHUNK_PROSE = 50;

const LANGUAGES = {
  vi: "Vietnamese",
  fr: "French",
  ja: "Japanese",
};

const TRANSLATABLE_FRONTMATTER_KEYS = new Set([
  "title", "description", "details", "name", "tagline",
  "label", "text", "placeholder", "hero",
]);

// ============================================================
// CLI
// ============================================================

const { values: opts } = parseArgs({
  options: {
    langs: { type: "string", default: Object.keys(LANGUAGES).join(",") },
    docs: { type: "string", default: DOCS_DIR },
    workers: { type: "string", default: String(WORKERS) },
    "dry-run": { type: "boolean", default: false },
    "clear-cache": { type: "boolean", default: false },
    force: { type: "boolean", default: false },
    strict: { type: "boolean", default: false },
    "skip-validation": { type: "boolean", default: false },
    help: { type: "boolean", short: "h", default: false },
  },
  strict: false,
  allowPositionals: true,
});

if (opts.help) {
  console.log(`VitePress Markdown Translator

Usage:
  node translate.mjs [options]

Options:
  --langs <list>      Comma-separated target languages (default: ${Object.keys(LANGUAGES).join(",")})
  --docs <path>       Source docs directory (default: docs/)
  --workers <n>       Parallel workers (default: ${WORKERS})
  --dry-run           Show what would be translated without API calls
  --clear-cache       Delete translation cache before starting
  --force             Force retranslation (still uses string cache)
  --strict            Fail on any translation error
  --skip-validation   Skip API key validation
  --help              Show this help`);
  process.exit(0);
}

// ============================================================
// HELPERS
// ============================================================

function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
}

function fileHash(filePath) {
  return sha256(readFileSync(filePath));
}

function mkdirp(dir) {
  mkdirSync(dir, { recursive: true });
}

function atomicWrite(filePath, content) {
  mkdirp(dirname(filePath));
  const tmp = join(dirname(filePath), `.tmp-${Date.now()}-${Math.random().toString(36).slice(2)}.tmp`);
  try {
    writeFileSync(tmp, content, "utf-8");
    renameSync(tmp, filePath);
  } catch (e) {
    try { unlinkSync(tmp); } catch {}
    throw e;
  }
}

function loadJson(filePath) {
  if (!existsSync(filePath)) return {};
  try {
    return JSON.parse(readFileSync(filePath, "utf-8"));
  } catch {
    return {};
  }
}

function saveJson(filePath, data) {
  atomicWrite(filePath, JSON.stringify(data, null, 2));
}

// ============================================================
// CACHE
// ============================================================

function cacheKey(text, targetLang) {
  const norm = text.trim().replace(/\s+/g, " ");
  const raw = JSON.stringify({
    v: CACHE_VERSION, m: MODEL, s: "en",
    t: targetLang, text: norm, len: text.length,
  });
  return sha256(raw);
}

function loadCache() {
  const data = loadJson(CACHE_FILE);
  if (data.version !== CACHE_VERSION) {
    return { version: CACHE_VERSION, entries: {} };
  }
  if (!data.entries) data.entries = {};
  return data;
}

function saveCache(cache) {
  saveJson(CACHE_FILE, cache);
}

function cacheGet(cache, text, target) {
  const key = cacheKey(text, target);
  const entry = cache.entries[key];
  if (entry && typeof entry.translation === "string") {
    return entry.translation;
  }
  return null;
}

function cachePut(cache, text, target, translation) {
  cache.entries[cacheKey(text, target)] = {
    source: text, target,
    translation, ts: Math.floor(Date.now() / 1000),
  };
}

// ============================================================
// PAGE STATE
// ============================================================

function loadState() {
  const data = loadJson(STATE_FILE);
  if (data.version !== CACHE_VERSION) {
    return { version: CACHE_VERSION, pages: {} };
  }
  if (!data.pages) data.pages = {};
  return data;
}

function saveState(state) {
  saveJson(STATE_FILE, state);
}

function pageNeedsTranslation(state, rel, h, lang, force) {
  if (force) return true;
  const entry = state.pages[`${lang}:${rel}`];
  return !entry || entry.hash !== h;
}

function pageMarkDone(state, rel, h, lang) {
  state.pages[`${lang}:${rel}`] = { hash: h, ts: Math.floor(Date.now() / 1000) };
}

// ============================================================
// MARKDOWN PROTECTION (Placeholder System)
// ============================================================

class Protector {
  constructor() {
    this._items = [];
  }

  _placeholder(idx) {
    return `__PH_${idx}__`;
  }

  protect(text) {
    const regions = [];

    const add = (pattern, flags = "") => {
      const re = new RegExp(pattern, flags);
      let m;
      while ((m = re.exec(text)) !== null) {
        regions.push([m.index, m.index + m[0].length, m[0]]);
      }
    };

    // Block-level protections
    add("````[\\s\\S]*?````");
    add("```[\\s\\S]*?```");
    add("~~~~[\\s\\S]*?~~~~");
    add("~~~[\\s\\S]*?~~~");

    // VitePress containers
    add("^:::\\s*(?:tip|info|warning|danger|details)\\b.*?^:::", "gm");

    // HTML blocks
    add("<script[\\s\\S]*?</script>", "i");
    add("<style[\\s\\S]*?</style>", "i");
    add("<!--[\\s\\S]*?-->", "i");

    // Vue/VitePress components
    add("<[A-Z][a-zA-Z0-9]*(?:\\s[^>]*)?\\s*/>");
    add("<[A-Z][a-zA-Z0-9]*(?:\\s[^>]*)?>[\\s\\S]*?</[A-Z][a-zA-Z0-9]*>");

    // HTML tags with content
    const htmlTags = [
      "div", "p", "span", "section", "article", "header", "footer",
      "nav", "main", "aside", "figure", "figcaption", "blockquote",
      "li", "td", "th", "h[1-6]", "iframe", "table", "thead", "tbody",
      "video", "audio", "source",
    ];
    for (const tag of htmlTags) {
      add(`<${tag}\\b[^>]*>[\\s\\S]*?</${tag}>`, "i");
    }

    // Self-closing HTML tags
    add("<(?:img|br|hr|input|source|link|meta)\\b[^>]*/?>", "i");

    // Sort by start, remove overlaps
    regions.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
    const merged = [];
    for (const [s, e, content] of regions) {
      if (merged.length && s < merged[merged.length - 1][1]) continue;
      merged.push([s, e, content]);
    }

    // Find unprotected regions
    const unprotected = [];
    let pos = 0;
    for (const [s, e] of merged) {
      if (s > pos) unprotected.push([pos, s]);
      pos = e;
    }
    if (pos < text.length) unprotected.push([pos, text.length]);

    // Inline protections
    const inline = [];
    for (const [urS, urE] of unprotected) {
      const region = text.slice(urS, urE);

      let m;

      // Inline code
      const reInline = /`[^`\n]+`/g;
      while ((m = reInline.exec(region))) {
        inline.push([urS + m.index, urS + m.index + m[0].length, m[0]]);
      }

      // Images
      const reImage = /!\[[^\]]*\]\([^)]+\)/g;
      while ((m = reImage.exec(region))) {
        inline.push([urS + m.index, urS + m.index + m[0].length, m[0]]);
      }

      // Autolinks
      const reAuto = /<(https?:\/\/[^>]+)>/g;
      while ((m = reAuto.exec(region))) {
        inline.push([urS + m.index, urS + m.index + m[0].length, m[0]]);
      }

      // Reference links
      const reRef = /\[[^\]]+\]\[[^\]]*\]/g;
      while ((m = reRef.exec(region))) {
        inline.push([urS + m.index, urS + m.index + m[0].length, m[0]]);
      }

      // VitePress template expressions
      const reTemplate = /\{\{[^}]+\}\}/g;
      while ((m = reTemplate.exec(region))) {
        inline.push([urS + m.index, urS + m.index + m[0].length, m[0]]);
      }

      // Links: protect URL part
      const reLink = /\[([^\]]+)\]\(([^)]+)\)/g;
      while ((m = reLink.exec(region))) {
        const fullS = urS + m.index;
        const fullE = urS + m.index + m[0].length;
        if (merged.some(([bs, be]) => fullS < bs && fullE > bs)) continue;
        const urlPartStart = urS + m.index + m[0].indexOf("](") + 1;
        const urlPart = m[0].slice(m[0].indexOf("]("));
        inline.push([urlPartStart, fullE, urlPart]);
      }
    }

    // Merge all regions
    const allRegions = [...merged, ...inline];
    allRegions.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
    const final = [];
    for (const [s, e, content] of allRegions) {
      if (final.length && s < final[final.length - 1][1]) continue;
      final.push([s, e, content]);
    }

    // Replace with placeholders
    const result = [];
    pos = 0;
    for (const [s, e, content] of final) {
      if (s > pos) result.push(text.slice(pos, s));
      const idx = this._items.length;
      this._items.push(content);
      result.push(this._placeholder(idx));
      pos = e;
    }
    if (pos < text.length) result.push(text.slice(pos));

    return result.join("");
  }

  restore(text) {
    for (let idx = 0; idx < this._items.length; idx++) {
      text = text.split(this._placeholder(idx)).join(this._items[idx]);
    }
    return text;
  }

  validateRestored(original, restored) {
    const errors = [];
    const remaining = restored.match(/__PH_\d+__/g);
    if (remaining) {
      errors.push(`Unrestored placeholders: ${remaining.slice(0, 5).join(", ")}`);
    }
    // Verify placeholder counts match
    const origCount = (original.match(/__PH_\d+__/g) || []).length;
    const restCount = (restored.match(/__PH_\d+__/g) || []).length;
    if (origCount !== restCount) {
      errors.push(`Placeholder count mismatch: ${origCount} → ${restCount}`);
    }
    return errors;
  }
}

function proseOnly(text) {
  return text
    .replace(/__PH_\d+__/g, "")
    .replace(/#{1,6}\s*/g, "")
    .replace(/[*_~`]/g, "")
    .trim();
}

// ============================================================
// FRONTMATTER
// ============================================================

function extractFrontmatter(md) {
  const m = md.match(/^(---\n.*?\n---\n?)/s);
  if (m) return [m[1], md.slice(m[0].length)];
  return [null, md];
}

async function translateFrontmatter(fm, targetLang, cache, stats) {
  const lines = fm.split("\n");
  const result = [];

  for (const line of lines) {
    let m;
    let keyPart, value, quote;

    // Try double-quoted
    m = line.match(/^(\s*-?\s*[a-zA-Z_-]+:\s+)"((?:\\.|[^"\\])*)"/);
    if (m) {
      keyPart = m[1]; value = m[2]; quote = '"';
      value = value.replace(/\\"/g, '"');
    } else {
      // Try single-quoted
      m = line.match(/^(\s*-?\s*[a-zA-Z_-]+:\s+)'((?:\\'|[^'\\])*)'/);
      if (m) {
        keyPart = m[1]; value = m[2]; quote = "'";
        value = value.replace(/\\'/g, "'");
      } else {
        // Try unquoted
        m = line.match(/^(\s*-?\s*[a-zA-Z_-]+:\s+)([^\n#]+?)(?:\s*#.*)?$/);
        if (m) {
          keyPart = m[1]; value = m[2].trim(); quote = null;
        } else {
          result.push(line);
          continue;
        }
      }
    }

    const keyName = keyPart.replace(/^\s*-?\s*/, "").trim().replace(/:$/, "").toLowerCase();
    if (!TRANSLATABLE_FRONTMATTER_KEYS.has(keyName) || value.trim().length < MIN_TEXT_LENGTH) {
      result.push(line);
      continue;
    }

    // Check cache
    let translated = cacheGet(cache, value, targetLang);
    if (translated !== null) {
      stats.cacheHits++;
    } else {
      translated = await callApi(value, targetLang);
      translated = postProcess(translated, targetLang);
      cachePut(cache, value, targetLang, translated);
      stats.apiRequests++;
    }

    let escaped;
    if (quote === '"') escaped = translated.replace(/"/g, '\\"');
    else if (quote === "'") escaped = translated.replace(/'/g, "\\'");
    else escaped = translated;

    const q = quote || '"';
    result.push(`${keyPart.trimEnd()} ${q}${escaped}${q}`);
  }

  return result.join("\n");
}

// ============================================================
// RATE LIMITING
// ============================================================

let rateLimitDelay = REQUEST_DELAY;
let lastRequestTime = 0;

async function waitForRateLimit() {
  const now = Date.now();
  const elapsed = now - lastRequestTime;
  if (elapsed < rateLimitDelay) {
    await new Promise(r => setTimeout(r, rateLimitDelay - elapsed));
  }
  lastRequestTime = Date.now();
}

function adjustRateLimit(success, statusCode) {
  if (success) {
    rateLimitDelay = Math.max(500, rateLimitDelay * 0.95);
  } else if (statusCode === 429) {
    rateLimitDelay = Math.min(10000, rateLimitDelay * 2);
    console.log(`      Rate limited, new delay: ${(rateLimitDelay / 1000).toFixed(1)}s`);
  } else {
    rateLimitDelay = Math.min(10000, rateLimitDelay * 1.5);
  }
}

// ============================================================
// API CALL + RETRY
// ============================================================

let openaiClient = null;

async function getOpenAIClient() {
  if (!openaiClient) {
    const { default: OpenAI } = await import("openai");
    openaiClient = new OpenAI({
      apiKey: API_KEY,
      baseURL: BASE_URL,
      timeout: TIMEOUT,
    });
  }
  return openaiClient;
}

async function callApi(text, targetLang) {
  const langFull = LANGUAGES[targetLang] || targetLang;
  const systemMsg =
    `Translate the following Markdown from English to ${langFull}. ` +
    `Translate only human-readable prose. ` +
    `Preserve all __PH_N__ placeholders exactly as they appear. ` +
    `Preserve all Markdown formatting, structure, and meaning. ` +
    `Return only the translated text with no explanations.`;

  let lastError = "Unknown error";

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    await waitForRateLimit();

    try {
      const client = await getOpenAIClient();
      const resp = await client.chat.completions.create({
        model: MODEL,
        messages: [
          { role: "system", content: systemMsg },
          { role: "user", content: text },
        ],
        temperature: 0.2,
        max_tokens: MAX_TOKENS,
      });

      const content = resp.choices[0]?.message?.content;
      if (!content || !content.trim()) {
        throw new Error("Empty translation");
      }

      adjustRateLimit(true);
      return content.trim();
    } catch (e) {
      lastError = e.message || String(e);

      // Check for permanent errors
      const status = e.status || e.statusCode;
      if (status && [400, 401, 403, 404, 422].includes(status)) {
        throw new Error(`API error ${status}: ${lastError.slice(0, 300)}`);
      }

      adjustRateLimit(false, status);
    }

    if (attempt < MAX_RETRIES) {
      const delay = RETRY_DELAYS[Math.min(attempt, RETRY_DELAYS.length - 1)];
      console.log(`      Retry ${attempt + 1}/${MAX_RETRIES} after ${delay}s (${lastError.slice(0, 80)})`);
      await new Promise(r => setTimeout(r, delay * 1000));
    }
  }

  throw new Error(`API failed after ${MAX_RETRIES} retries: ${lastError.slice(0, 200)}`);
}

// ============================================================
// POST-PROCESSING
// ============================================================

function postProcess(text, targetLang) {
  if (targetLang === "vi") {
    text = text.replace(/\s+([!?.,;:])/g, "$1");
    text = text.replace(/  +/g, " ");
  }
  text = text.replace(/\]\s*\(/g, "](");
  return text;
}

// ============================================================
// TRANSLATE MARKDOWN
// ============================================================

async function translateMarkdown(md, targetLang, cache, stats) {
  const [fm, body] = extractFrontmatter(md);

  // Protect non-translatable content
  const protector = new Protector();
  const protectedBody = protector.protect(body);

  // Check if there's any translatable prose
  const prose = proseOnly(protectedBody);
  if (prose.length < MIN_TEXT_LENGTH) {
    return { translated: md, failed: [] };
  }

  // Check cache
  const cached = cacheGet(cache, protectedBody, targetLang);
  let translatedBody;
  const failed = [];

  if (cached !== null) {
    stats.cacheHits++;
    translatedBody = cached;
  } else {
    stats.cacheMisses++;
    try {
      translatedBody = await callApi(protectedBody, targetLang);
      translatedBody = postProcess(translatedBody, targetLang);
      cachePut(cache, protectedBody, targetLang, translatedBody);
      stats.apiRequests++;
    } catch (e) {
      console.log(`      ERROR: ${e.message}`);
      translatedBody = protectedBody;
      failed.push(prose.slice(0, 60));
    }
  }

  // Restore placeholders
  const restoredBody = protector.restore(translatedBody);

  // Validate
  const validationErrors = protector.validateRestored(body, restoredBody);
  for (const err of validationErrors) {
    console.log(`      VALIDATION: ${err}`);
  }

  // Translate frontmatter
  let result;
  if (fm) {
    const translatedFm = await translateFrontmatter(fm, targetLang, cache, stats);
    result = translatedFm + restoredBody;
  } else {
    result = restoredBody;
  }

  return { translated: result, failed };
}

// ============================================================
// PATH FIXING
// ============================================================

function fixRelativePaths(md, sourceRel) {
  const parts = sourceRel.split(sep);
  const depth = parts.length - 1;
  if (depth <= 0) return md;

  const extra = "../".repeat(depth);

  return md
    .replace(/(?:from|require)\s*\(\s*['"](\.\.[^'"]+)['"]/g, (match, p1) => {
      if (p1.startsWith("../")) {
        return match.replace(p1, extra + p1);
      }
      return match;
    })
    .replace(/import\s+[^'"]*from\s*['"](\.\.[^'"]+)['"]/g, (match, p1) => {
      if (p1.startsWith("../")) {
        return match.replace(p1, extra + p1);
      }
      return match;
    });
}

// ============================================================
// PRE-VALIDATION
// ============================================================

function preValidatePages(pages, docsDir) {
  const issues = {};
  for (const mdPath of pages) {
    const rel = relative(docsDir, mdPath);
    const relIssues = [];
    const body = readFileSync(mdPath, "utf-8");

    // Check for pre-existing placeholders
    const placeholderCount = (body.match(/__PH_\d+__/g) || []).length;
    if (placeholderCount > 0) {
      relIssues.push(`Already has ${placeholderCount} placeholders (will break)`);
    }

    // Check for malformed code blocks
    if ((body.match(/```/g) || []).length % 2 !== 0) {
      relIssues.push("Unmatched backticks (code block)");
    }

    if (relIssues.length) {
      issues[rel] = relIssues;
    }
  }
  return issues;
}

// ============================================================
// FILE DISCOVERY
// ============================================================

function findSourcePages(docsDir, langDirs) {
  const allMd = readdirSync(docsDir, { recursive: true, encoding: "utf-8" })
    .filter(f => f.endsWith(".md"))
    .map(f => join(docsDir, f));

  const pages = [];
  for (const mdPath of allMd) {
    const rel = relative(docsDir, mdPath);
    const parts = rel.split(sep);
    if (parts[0] && langDirs.has(parts[0])) continue;
    if (parts.includes(".vitepress")) continue;
    if (basename(mdPath).includes("[")) continue;
    pages.push(mdPath);
  }

  return pages.sort();
}

function basename(filePath) {
  return filePath.split(sep).pop();
}

// ============================================================
// MAIN
// ============================================================

async function main() {
  // API key check
  if (!opts["dry-run"] && !API_KEY) {
    console.log("ERROR: TRANSLATION_API_KEY (or NVIDIA_API_KEY) is not set.\n");
    console.log('Run: export TRANSLATION_API_KEY="nvapi-..."\n');
    console.log("For Cloudflare Pages:");
    console.log("  1. Go to Pages -> your project -> Settings -> Build");
    console.log("  2. Add build variable: TRANSLATION_API_KEY = nvapi-...");
    process.exit(1);
  }

  // Validate API key
  if (!opts["dry-run"] && !opts["skip-validation"] && API_KEY) {
    const validationCache = join(DOCS_DIR, ".vitepress", ".api-validation");
    let validationAge = 0;
    if (existsSync(validationCache)) {
      validationAge = (Date.now() - statSync(validationCache).mtimeMs) / 1000;
    }

    if (validationAge > 86400 || !existsSync(validationCache)) {
      console.log("Validating API key...");
      try {
        const client = await getOpenAIClient();
        await client.chat.completions.create({
          model: MODEL,
          messages: [{ role: "user", content: "Hello" }],
          max_tokens: 10,
        });
        console.log("API key OK.");
        mkdirp(dirname(validationCache));
        writeFileSync(validationCache, "");
      } catch (e) {
        const errStr = String(e);
        if (errStr.includes("403") || errStr.includes("401")) {
          console.log(`ERROR: API key is invalid or expired: ${e.message}`);
          process.exit(1);
        }
        console.log(`WARNING: Could not validate API key: ${e.message}`);
      }
    } else {
      console.log(`API key validation cached (${(validationAge / 3600).toFixed(1)}h ago)`);
    }
  } else if (opts["skip-validation"]) {
    console.log("Skipping API key validation (--skip-validation)");
  }

  // Clear cache
  if (opts["clear-cache"]) {
    for (const f of [CACHE_FILE, STATE_FILE]) {
      if (existsSync(f)) {
        unlinkSync(f);
        console.log(`Deleted: ${f}`);
      }
    }
  }

  const docsDir = resolve(opts.docs);
  if (!existsSync(docsDir) || !statSync(docsDir).isDirectory()) {
    console.log(`ERROR: docs directory not found: ${docsDir}`);
    process.exit(1);
  }

  const langDirs = new Set(Object.keys(LANGUAGES));
  const requested = opts.langs.split(",").map(s => s.trim()).filter(Boolean);
  for (const lang of requested) {
    if (!LANGUAGES[lang]) {
      console.log(`ERROR: unknown language '${lang}'`);
      console.log(`Supported: ${Object.keys(LANGUAGES).join(", ")}`);
      process.exit(1);
    }
  }

  const workers = parseInt(opts.workers, 10) || WORKERS;
  const pages = findSourcePages(docsDir, langDirs);
  const state = loadState();
  const cache = loadCache();

  console.log();
  console.log("VitePress Markdown Translator");
  console.log("=".repeat(50));
  console.log(`Source:    ${docsDir}`);
  console.log(`Pages:     ${pages.length}`);
  console.log(`Languages: ${requested.join(", ")}`);
  console.log(`Workers:   ${workers}`);
  console.log(`Model:     ${MODEL}`);
  console.log();

  if (opts["dry-run"]) {
    console.log("DRY RUN: no API calls will be made.\n");
  }

  // Pre-validate
  if (!opts["dry-run"]) {
    const validationIssues = preValidatePages(pages, docsDir);
    if (Object.keys(validationIssues).length > 0) {
      console.log("VALIDATION ERRORS:");
      for (const [rel, errs] of Object.entries(validationIssues)) {
        console.log(`  ${rel}:`);
        for (const err of errs) console.log(`    - ${err}`);
      }
      if (opts.strict) process.exit(1);
    }
  }

  const stats = { cacheHits: 0, cacheMisses: 0, apiRequests: 0 };
  const buildStart = Date.now();

  for (const lang of requested) {
    console.log(`[${lang}] ${LANGUAGES[lang]}`);

    let pagesSkipped = 0;
    let pagesTranslated = 0;
    const tasks = [];

    for (const mdPath of pages) {
      const rel = relative(docsDir, mdPath);
      const h = fileHash(mdPath);
      if (!pageNeedsTranslation(state, rel, h, lang, opts.force)) {
        pagesSkipped++;
        if (!opts["dry-run"]) console.log(`  ${rel.padEnd(50)} SKIP`);
        continue;
      }
      pagesTranslated++;
      if (opts["dry-run"]) {
        console.log(`  ${rel.padEnd(50)} WOULD TRANSLATE`);
      } else {
        tasks.push([mdPath, h]);
      }
    }

    console.log(`  pages skipped: ${pagesSkipped}`);
    console.log(`  pages changed: ${pagesTranslated}`);

    if (!opts["dry-run"] && tasks.length > 0) {
      const langFailures = [];
      const processTask = async ([mdPath, h]) => {
        const rel = relative(docsDir, mdPath);
        const t0 = Date.now();
        const md = readFileSync(mdPath, "utf-8");
        const { translated, failed } = await translateMarkdown(md, lang, cache, stats);
        const fixed = fixRelativePaths(translated, rel);
        const outDir = join(docsDir, lang, dirname(rel));
        mkdirp(outDir);
        atomicWrite(join(outDir, basename(mdPath)), fixed);
        const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
        pageMarkDone(state, rel, h, lang);
        console.log(`  ${rel.padEnd(50)} DONE (${elapsed}s)`);
        return { rel, success: failed.length === 0, failed };
      };

      if (workers <= 1) {
        for (const task of tasks) {
          try {
            const r = await processTask(task);
            if (r.failed.length) langFailures.push(...r.failed);
          } catch (e) {
            console.log(`  ERROR: ${e.message}`);
            if (opts.strict) process.exit(1);
          }
        }
      } else {
        // Process with concurrency limit
        const queue = [...tasks];
        const running = new Set();

        const runNext = async () => {
          if (queue.length === 0) return;
          const task = queue.shift();
          const p = processTask(task).then(r => {
            if (r.failed.length) langFailures.push(...r.failed);
          }).catch(e => {
            console.log(`  ERROR: ${e.message}`);
            if (opts.strict) process.exit(1);
          }).finally(() => {
            running.delete(p);
            return runNext();
          });
          running.add(p);
        };

        // Start initial batch
        const initial = Math.min(workers, queue.length);
        const starters = [];
        for (let i = 0; i < initial; i++) {
          starters.push(runNext());
        }
        await Promise.all(starters);
        // Wait for all remaining
        while (running.size > 0) {
          await Promise.race([...running]);
        }
      }

      if (langFailures.length) {
        console.log(`\n  WARNING: ${langFailures.length} string(s) fell back or failed`);
      }

      saveCache(cache);
      saveState(state);
    }

    console.log();
  }

  const buildElapsed = ((Date.now() - buildStart) / 1000).toFixed(1);

  console.log("=".repeat(50));
  console.log("Translation complete.\n");
  console.log(`Total time:      ${buildElapsed}s`);
  console.log(`Pages scanned:   ${pages.length * requested.length}`);
  console.log(`Cache hits:      ${stats.cacheHits}`);
  console.log(`Cache misses:    ${stats.cacheMisses}`);
  console.log(`API requests:    ${stats.apiRequests}\n`);
  console.log(`Cache:  ${CACHE_FILE}`);
  console.log(`State:  ${STATE_FILE}`);
  console.log(`Output: ${docsDir}/{lang}/`);
  if (opts.strict) console.log("Mode:   STRICT (errors cause exit)");
  console.log();
}

main().catch(e => {
  console.error(`FATAL: ${e.message}`);
  process.exit(1);
});
