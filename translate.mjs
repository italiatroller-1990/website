#!/usr/bin/env node
/**
 * VitePress Markdown Translator (memory-optimized)
 *
 * Translates English Markdown source files in docs/ to target languages
 * using NVIDIA NIM (OpenAI-compatible API).
 *
 * Memory design:
 * - Workers receive file paths, not preloaded content
 * - Cache stores only translation (not source text)
 * - Protector clears items after restore
 * - Hash-only checks read minimal data
 * - No unbounded arrays of page content
 */

import { createHash } from "node:crypto";
import {
  createReadStream,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  unlinkSync,
  writeFileSync,
  statSync,
} from "node:fs";
import { join, dirname, resolve, relative, sep, basename as pathBasename } from "node:path";
import { parseArgs } from "node:util";
import { createInterface } from "node:readline";

// ============================================================
// CONFIGURATION
// ============================================================

const DOCS_DIR = join(process.cwd(), "docs");
const CACHE_FILE = join(DOCS_DIR, ".vitepress", "translation-cache.json");
const STATE_FILE = join(DOCS_DIR, ".vitepress", "translation-state.json");

const API_KEY = (process.env.TRANSLATION_API_KEY || process.env.NVIDIA_API_KEY || "").trim();
const BASE_URL = process.env.TRANSLATION_BASE_URL || "https://integrate.api.nvidia.com/v1";
const MODEL = process.env.TRANSLATION_MODEL || "poolside/laguna-xs-2.1";
const WORKERS = parseInt(process.env.TRANSLATION_WORKERS || "2", 10);
const TIMEOUT = parseInt(process.env.TRANSLATION_TIMEOUT || "120", 10) * 1000;
const MAX_RETRIES = parseInt(process.env.TRANSLATION_MAX_RETRIES || "5", 10);
const RETRY_DELAYS = [2, 4, 8, 16, 32];

const CACHE_VERSION = 8;
const REQUEST_DELAY = 1500;
const MAX_TOKENS = 8192;
const MIN_TEXT_LENGTH = 2;

const LANGUAGES = { vi: "Vietnamese", fr: "French", ja: "Japanese" };
const TRANSLATABLE_FM_KEYS = new Set([
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

Usage: node translate.mjs [options]

Options:
  --langs <list>      Languages (default: ${Object.keys(LANGUAGES).join(",")})
  --docs <path>       Source docs dir (default: docs/)
  --workers <n>       Workers (default: ${WORKERS})
  --dry-run           Dry run
  --clear-cache       Clear cache
  --force             Force retranslate
  --strict            Fail on errors
  --skip-validation   Skip API validation`);
  process.exit(0);
}

// ============================================================
// HELPERS
// ============================================================

function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
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
  try { return JSON.parse(readFileSync(filePath, "utf-8")); }
  catch { return {}; }
}

function saveJson(filePath, data) {
  atomicWrite(filePath, JSON.stringify(data));
}

/** Streaming file hash – reads file in chunks, never loads full file for hashing */
function fileHashStream(filePath) {
  return new Promise((resolve, reject) => {
    const h = createHash("sha256");
    const s = createReadStream(filePath);
    s.on("data", (chunk) => h.update(chunk));
    s.on("end", () => resolve(h.digest("hex")));
    s.on("error", reject);
  });
}

// ============================================================
// CACHE (minimal memory footprint)
// ============================================================

// Cache key: hash of (version, model, lang, normalized-text, length)
// Cache value: { r: translation, ts: timestamp } — NO source stored
function cacheKey(text, targetLang) {
  const raw = `${CACHE_VERSION}:${MODEL}:en:${targetLang}:${text.length}:${sha256(text.trim().replace(/\s+/g, " "))}`;
  return sha256(raw);
}

function loadCache() {
  const data = loadJson(CACHE_FILE);
  if (data.v !== CACHE_VERSION || !data.e) return { v: CACHE_VERSION, e: {} };
  return data;
}

function saveCache(cache) {
  saveJson(CACHE_FILE, cache);
}

function cacheGet(cache, text, target) {
  const entry = cache.e[cacheKey(text, target)];
  return entry && typeof entry.r === "string" ? entry.r : null;
}

function cachePut(cache, text, target, translation) {
  cache.e[cacheKey(text, target)] = {
    r: translation,
    ts: Math.floor(Date.now() / 1000),
  };
}

// ============================================================
// PAGE STATE
// ============================================================

function loadState() {
  const data = loadJson(STATE_FILE);
  if (data.v !== CACHE_VERSION || !data.p) return { v: CACHE_VERSION, p: {} };
  return data;
}

function saveState(state) {
  saveJson(STATE_FILE, state);
}

function pageNeedsTranslation(state, rel, h, lang, force) {
  if (force) return true;
  const entry = state.p[`${lang}:${rel}`];
  return !entry || entry.h !== h;
}

function pageMarkDone(state, rel, h, lang) {
  state.p[`${lang}:${rel}`] = { h, ts: Math.floor(Date.now() / 1000) };
}

// ============================================================
// MARKDOWN PROTECTION
// ============================================================

function protect(text) {
  const regions = [];
  const add = (pattern, flags = "") => {
    const re = new RegExp(pattern, flags);
    let m;
    while ((m = re.exec(text)) !== null) {
      regions.push([m.index, m.index + m[0].length]);
    }
  };

  // Block-level
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
  // HTML blocks
  for (const tag of ["div","p","span","section","article","header","footer","nav","main","aside","figure","figcaption","blockquote","li","td","th","h[1-6]","iframe","table","thead","tbody","video","audio","source"]) {
    add(`<${tag}\\b[^>]*>[\\s\\S]*?</${tag}>`, "i");
  }
  // Self-closing
  add("<(?:img|br|hr|input|source|link|meta)\\b[^>]*/?>", "i");

  // Deduplicate overlapping regions
  regions.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  const merged = [];
  for (const [s, e] of regions) {
    if (merged.length && s < merged[merged.length - 1][1]) continue;
    merged.push([s, e]);
  }

  // Find unprotected gaps
  const gaps = [];
  let pos = 0;
  for (const [s, e] of merged) {
    if (s > pos) gaps.push([pos, s]);
    pos = e;
  }
  if (pos < text.length) gaps.push([pos, text.length]);

  // Inline protections within gaps
  const inline = [];
  for (const [gS, gE] of gaps) {
    const region = text.slice(gS, gE);
    let m;
    const reInline = /`[^`\n]+`/g;
    while ((m = reInline.exec(region))) inline.push([gS + m.index, gS + m.index + m[0].length]);
    const reImage = /!\[[^\]]*\]\([^)]+\)/g;
    while ((m = reImage.exec(region))) inline.push([gS + m.index, gS + m.index + m[0].length]);
    const reAuto = /<(https?:\/\/[^>]+)>/g;
    while ((m = reAuto.exec(region))) inline.push([gS + m.index, gS + m.index + m[0].length]);
    const reRef = /\[[^\]]+\]\[[^\]]*\]/g;
    while ((m = reRef.exec(region))) inline.push([gS + m.index, gS + m.index + m[0].length]);
    const reTemplate = /\{\{[^}]+\}\}/g;
    while ((m = reTemplate.exec(region))) inline.push([gS + m.index, gS + m.index + m[0].length]);
    // Link URL part
    const reLink = /\[([^\]]+)\]\(([^)]+)\)/g;
    while ((m = reLink.exec(region))) {
      const fullS = gS + m.index;
      const fullE = gS + m.index + m[0].length;
      if (merged.some(([bs, be]) => fullS < be && fullE > bs)) continue;
      const urlStart = gS + m.index + m[0].indexOf("](") + 1;
      inline.push([urlStart, fullE]);
    }
  }

  // Merge all
  const all = [...merged, ...inline];
  all.sort((a, b) => a[0] - b[0] || b[1] - b[1]);
  const final = [];
  for (const [s, e] of all) {
    if (final.length && s < final[final.length - 1][1]) continue;
    final.push([s, e]);
  }

  // Build protected text and items map (idx → original text)
  const items = new Map();
  const parts = [];
  pos = 0;
  for (const [s, e] of final) {
    if (s > pos) parts.push(text.slice(pos, s));
    const idx = items.size;
    items.set(idx, text.slice(s, e));
    parts.push(`__PH_${idx}__`);
    pos = e;
  }
  if (pos < text.length) parts.push(text.slice(pos));

  return { text: parts.join(""), items };
}

function restore(text, items) {
  if (items.size === 0) return text;
  // Single-pass replacement using sorted entries
  const entries = [...items.entries()].sort((a, b) => b[0] - a[0]);
  let result = text;
  for (const [idx, original] of entries) {
    result = result.split(`__PH_${idx}__`).join(original);
  }
  return result;
}

function validatePlaceholders(original, restored) {
  const origMatches = original.match(/__PH_\d+__/g);
  const restMatches = restored.match(/__PH_\d+__/g);
  const origSet = new Map();
  if (origMatches) for (const m of origMatches) origSet.set(m, (origSet.get(m) || 0) + 1);
  const restSet = new Map();
  if (restMatches) for (const m of restMatches) restSet.set(m, (restSet.get(m) || 0) + 1);

  const errors = [];
  // Every original must appear exactly once in restored
  for (const [ph, count] of origSet) {
    const inRest = restSet.get(ph) || 0;
    if (inRest === 0) errors.push(`Missing placeholder: ${ph}`);
    else if (inRest !== 1) errors.push(`${ph} appears ${inRest}x (expected 1)`);
  }
  // No unknown placeholders
  for (const [ph] of restSet) {
    if (!origSet.has(ph)) errors.push(`Unknown placeholder: ${ph}`);
  }
  return errors;
}

function proseLength(text) {
  return text.replace(/__PH_\d+__/g, "").replace(/#{1,6}\s*/g, "").replace(/[*_~`]/g, "").trim().length;
}

// ============================================================
// FRONTMATTER
// ============================================================

function extractFrontmatter(md) {
  if (!md.startsWith("---\n")) return [null, md];
  const end = md.indexOf("\n---\n", 4);
  if (end === -1) return [null, md];
  return [md.slice(0, end + 5), md.slice(end + 5)];
}

async function translateFrontmatter(fm, targetLang, cache, stats) {
  const lines = fm.split("\n");
  const result = [];
  for (const line of lines) {
    let m;
    let keyPart, value, quote;

    m = line.match(/^(\s*-?\s*[a-zA-Z_-]+:\s+)"((?:\\.|[^"\\])*)"/);
    if (m) { keyPart = m[1]; value = m[2].replace(/\\"/g, '"'); quote = '"'; }
    else {
      m = line.match(/^(\s*-?\s*[a-zA-Z_-]+:\s+)'((?:\\'|[^'\\])*)'/);
      if (m) { keyPart = m[1]; value = m[2].replace(/\\'/g, "'"); quote = "'"; }
      else {
        m = line.match(/^(\s*-?\s*[a-zA-Z_-]+:\s+)([^\n#]+?)(?:\s*#.*)?$/);
        if (m) { keyPart = m[1]; value = m[2].trim(); quote = null; }
        else { result.push(line); continue; }
      }
    }

    const keyName = keyPart.replace(/^\s*-?\s*/, "").trim().replace(/:$/, "").toLowerCase();
    if (!TRANSLATABLE_FM_KEYS.has(keyName) || value.trim().length < MIN_TEXT_LENGTH) {
      result.push(line);
      continue;
    }

    let translated = cacheGet(cache, value, targetLang);
    if (translated !== null) {
      stats.cacheHits++;
    } else {
      translated = await callApi(value, targetLang);
      translated = postProcess(translated, targetLang);
      cachePut(cache, value, targetLang, translated);
      stats.apiRequests++;
    }

    const q = quote || '"';
    const escaped = q === '"' ? translated.replace(/"/g, '\\"') :
                    q === "'" ? translated.replace(/'/g, "\\'") : translated;
    result.push(`${keyPart.trimEnd()} ${q}${escaped}${q}`);
  }
  return result.join("\n");
}

// ============================================================
// RATE LIMITING
// ============================================================

let rateLimitDelay = REQUEST_DELAY;
let lastRequestTime = 0;

function waitForRateLimit() {
  const now = Date.now();
  const elapsed = now - lastRequestTime;
  const wait = Math.max(0, rateLimitDelay - elapsed);
  return new Promise((r) => setTimeout(r, wait)).then(() => { lastRequestTime = Date.now(); });
}

function adjustRateLimit(success, status) {
  if (success) rateLimitDelay = Math.max(500, rateLimitDelay * 0.95);
  else if (status === 429) rateLimitDelay = Math.min(10000, rateLimitDelay * 2);
  else rateLimitDelay = Math.min(10000, rateLimitDelay * 1.5);
}

// ============================================================
// API CALL
// ============================================================

let openaiClient = null;

async function getOpenAIClient() {
  if (!openaiClient) {
    const { default: OpenAI } = await import("openai");
    openaiClient = new OpenAI({ apiKey: API_KEY, baseURL: BASE_URL, timeout: TIMEOUT });
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
        temperature: 1,
        top_p: 0.95,
        max_tokens: MAX_TOKENS,
        stream: false,
      });

      const content = resp.choices[0]?.message?.content;
      if (!content || !content.trim()) throw new Error("Empty translation");

      // Release resp reference
      const trimmed = content.trim();
      adjustRateLimit(true);
      return trimmed;
    } catch (e) {
      lastError = e.message || String(e);
      const status = e.status || e.statusCode;
      if (status && [400, 401, 403, 404, 422].includes(status)) {
        throw new Error(`API error ${status}: ${lastError.slice(0, 300)}`);
      }
      adjustRateLimit(false, status);
    }

    if (attempt < MAX_RETRIES) {
      const delay = RETRY_DELAYS[Math.min(attempt, RETRY_DELAYS.length - 1)];
      console.log(`      Retry ${attempt + 1}/${MAX_RETRIES} after ${delay}s (${lastError.slice(0, 80)})`);
      await new Promise((r) => setTimeout(r, delay * 1000));
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
  return text.replace(/\]\s*\(/g, "](");
}

// ============================================================
// TRANSLATE ONE PAGE
// ============================================================

async function translateOnePage(mdPath, lang, cache, stats, strict) {
  const md = readFileSync(mdPath, "utf-8");
  const [fm, body] = extractFrontmatter(md);

  // Protect
  const { text: protectedBody, items } = protect(body);

  // Check translatable prose
  if (proseLength(protectedBody) < MIN_TEXT_LENGTH) {
    return { translated: md, failed: false };
  }

  // Check cache
  let translatedBody = cacheGet(cache, protectedBody, lang);
  if (translatedBody !== null) {
    stats.cacheHits++;
  } else {
    stats.cacheMisses++;
    translatedBody = await callApi(protectedBody, lang);
    translatedBody = postProcess(translatedBody, lang);
    cachePut(cache, protectedBody, lang, translatedBody);
    stats.apiRequests++;
  }

  // Restore placeholders
  const restoredBody = restore(translatedBody, items);

  // Validate
  const errors = validatePlaceholders(protectedBody, restoredBody);
  if (errors.length > 0) {
    for (const err of errors) console.log(`      VALIDATION: ${err}`);
    if (strict) throw new Error(`Validation failed for ${mdPath}: ${errors[0]}`);
    // Fall back to original protected text (with placeholders intact)
    return { translated: (fm || "") + restore(protectedBody, items), failed: true };
  }

  // Translate frontmatter (must be awaited)
  let result;
  if (fm) {
    const translatedFm = await translateFrontmatter(fm, lang, cache, stats);
    result = translatedFm + restoredBody;
  } else {
    result = restoredBody;
  }

  // Release references
  return { translated: result, failed: false };
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
    .replace(/(?:from|require)\s*\(\s*['"](\.\.[^'"]+)['"]/g, (m, p1) => m.replace(p1, extra + p1))
    .replace(/import\s+[^'"]*from\s*['"](\.\.[^'"]+)['"]/g, (m, p1) => m.replace(p1, extra + p1));
}

// ============================================================
// PRE-VALIDATION (streaming, minimal memory)
// ============================================================

async function preValidatePage(mdPath) {
  const rel = relative(DOCS_DIR, mdPath);
  const issues = [];
  let backtickCount = 0;
  let placeholderCount = 0;

  const rl = createInterface({ input: createReadStream(mdPath, "utf-8"), crlfDelay: Infinity });
  for await (const line of rl) {
    // Count backticks (rough check)
    for (let i = 0; i < line.length - 2; i++) {
      if (line[i] === "`" && line[i+1] === "`" && line[i+2] === "`") backtickCount++;
    }
    // Count placeholders
    const ph = line.match(/__PH_\d+__/g);
    if (ph) placeholderCount += ph.length;
  }
  rl.close();

  if (placeholderCount > 0) issues.push(`Already has ${placeholderCount} placeholders`);
  if (backtickCount % 2 !== 0) issues.push("Unmatched code blocks");
  return issues.length ? { rel, issues } : null;
}

// ============================================================
// FILE DISCOVERY
// ============================================================

function findSourcePages(docsDir, langDirs) {
  const allMd = readdirSync(docsDir, { recursive: true, encoding: "utf-8" })
    .filter((f) => f.endsWith(".md"))
    .map((f) => join(docsDir, f));

  const pages = [];
  for (const mdPath of allMd) {
    const rel = relative(docsDir, mdPath);
    const parts = rel.split(sep);
    if (parts[0] && langDirs.has(parts[0])) continue;
    if (parts.includes(".vitepress")) continue;
    if (pathBasename(mdPath).includes("[")) continue;
    pages.push(mdPath);
  }
  return pages.sort();
}

// ============================================================
// WORKER POOL (bounded concurrency, file-path based)
// ============================================================

async function runWorkerPool(tasks, workers, processFn, strict) {
  let failureCount = 0;
  const queue = [...tasks];
  const running = new Set();
  let rejecting = false;

  const runNext = async () => {
    if (queue.length === 0 || rejecting) return;
    const task = queue.shift();
    const p = processFn(task)
      .catch((e) => {
        console.log(`      ERROR: ${e.message}`);
        failureCount++;
        if (strict) rejecting = true;
      })
      .finally(() => {
        running.delete(p);
        if (!rejecting && queue.length > 0) return runNext();
      });
    running.add(p);
  };

  // Start initial batch
  const initial = Math.min(workers, queue.length);
  for (let i = 0; i < initial; i++) runNext();

  // Drain
  while (running.size > 0) {
    await Promise.race([...running]);
  }

  return failureCount;
}

// ============================================================
// MAIN
// ============================================================

async function main() {
  // API key
  if (!opts["dry-run"] && !API_KEY) {
    console.log("ERROR: NVIDIA_API_KEY (or TRANSLATION_API_KEY) is not set.\n");
    console.log('Run: export NVIDIA_API_KEY="nvapi-..."\n');
    console.log("For Cloudflare Pages:");
    console.log("  1. Pages -> your project -> Settings -> Build");
    console.log("  2. Add build variable: NVIDIA_API_KEY = nvapi-...");
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
        if (String(e).includes("403") || String(e).includes("401")) {
          console.log(`ERROR: API key invalid or expired: ${e.message}`);
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
      if (existsSync(f)) { unlinkSync(f); console.log(`Deleted: ${f}`); }
    }
  }

  const docsDir = resolve(opts.docs);
  if (!existsSync(docsDir) || !statSync(docsDir).isDirectory()) {
    console.log(`ERROR: docs directory not found: ${docsDir}`);
    process.exit(1);
  }

  const langDirs = new Set(Object.keys(LANGUAGES));
  const requested = opts.langs.split(",").map((s) => s.trim()).filter(Boolean);
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

  // Pre-validate (streaming)
  if (!opts["dry-run"]) {
    const issues = [];
    for (const mdPath of pages) {
      const result = await preValidatePage(mdPath);
      if (result) issues.push(result);
    }
    if (issues.length > 0) {
      console.log("VALIDATION ERRORS:");
      for (const { rel, issues: errs } of issues) {
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
      // Streaming hash for page-state check
      const h = await fileHashStream(mdPath);
      if (!pageNeedsTranslation(state, rel, h, lang, opts.force)) {
        pagesSkipped++;
        if (!opts["dry-run"]) console.log(`  ${rel.padEnd(50)} SKIP`);
        continue;
      }
      pagesTranslated++;
      if (opts["dry-run"]) {
        console.log(`  ${rel.padEnd(50)} WOULD TRANSLATE`);
      } else {
        tasks.push({ mdPath, rel, h });
      }
    }

    console.log(`  pages skipped: ${pagesSkipped}`);
    console.log(`  pages changed: ${pagesTranslated}`);

    if (!opts["dry-run"] && tasks.length > 0) {
      const processTask = async ({ mdPath, rel, h }) => {
        const t0 = Date.now();
        const { translated, failed } = await translateOnePage(mdPath, lang, cache, stats, opts.strict);
        const fixed = fixRelativePaths(translated, rel);
        const outPath = join(docsDir, lang, rel);
        atomicWrite(outPath, fixed);
        pageMarkDone(state, rel, h, lang);
        const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
        console.log(`  ${rel.padEnd(50)} DONE (${elapsed}s)`);
        // Release reference
        return null;
      };

      const failures = await runWorkerPool(tasks, workers, processTask, opts.strict);
      if (failures > 0) {
        console.log(`\n  FAILED: ${failures} page(s)`);
        if (opts.strict) process.exit(1);
      }

      // Save cache and state after each language
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

main().catch((e) => {
  console.error(`FATAL: ${e.message}`);
  process.exit(1);
});
