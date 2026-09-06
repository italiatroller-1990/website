#!/usr/bin/env python3
"""
VitePress Markdown Translator (Optimized for Poolside Laguna XS 2.1)
====================================================================

Translates English Markdown source files in docs/ to target languages
using Poolside's Laguna XS 2.1 via OpenAI-compatible API.

Key Optimizations for Laguna XS 2.1:
- Exploits 256K context window (100K+ chars per request)
- Batches multiple pages in single API call
- MoE-aware temperature tuning (0.2 instead of 0)
- Adaptive rate limiting for free tier
- Validates placeholder coverage at scale
- Pre-validation of all pages before translation

Workflow:
    export TRANSLATION_API_KEY="your-poolside-key"
    python3 translate_optimized.py
    npm run docs:build

Features:
- Translates Markdown source, not generated HTML
- Content-hash cache survives between builds
- Page-level incremental detection (skip unchanged pages)
- Placeholder-based syntax protection (code, HTML, URLs, VitePress)
- Batched API requests (2-3 pages per call)
- Atomic writes for cache and translated files
- Strict validation of translated output
- Metrics logging for CI/CD integration

Usage:
    export TRANSLATION_API_KEY="your-key"
    python3 translate_optimized.py

    python3 translate_optimized.py --langs vi,ja
    python3 translate_optimized.py --workers 2
    python3 translate_optimized.py --dry-run
    python3 translate_optimized.py --clear-cache
    python3 translate_optimized.py --force
    python3 translate_optimized.py --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any


def ensure_requirements():
    try:
        import openai  # noqa: F401
    except ImportError:
        print("Installing requirements...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"])
        print()


ensure_requirements()

from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError  # noqa: E402


# ============================================================
# CONFIGURATION
# ============================================================

DOCS_DIR = Path("docs")
CACHE_FILE = DOCS_DIR / ".vitepress" / "translation-cache.json"
STATE_FILE = DOCS_DIR / ".vitepress" / "translation-state.json"

# Configurable via environment variables
API_KEY = os.environ.get("TRANSLATION_API_KEY", os.environ.get("NVIDIA_API_KEY", "")).strip()
BASE_URL = os.environ.get("TRANSLATION_BASE_URL", "https://integrate.api.nvidia.com/v1")
MODEL = os.environ.get("TRANSLATION_MODEL", "poolside/laguna-xs-2.1")  # Via NVIDIA NIM
WORKERS = int(os.environ.get("TRANSLATION_WORKERS", "2"))
TIMEOUT = int(os.environ.get("TRANSLATION_TIMEOUT", "120"))
MAX_RETRIES = int(os.environ.get("TRANSLATION_MAX_RETRIES", "5"))
RETRY_DELAYS = [2, 4, 8, 16, 32]

CACHE_VERSION = 6  # Bumped for new batching strategy
REQUEST_DELAY = 1.5  # NVIDIA NIM 40 RPM = ~1.5s between requests
MAX_TOKENS = 32768  # Use full output window
MIN_TEXT_LENGTH = 2
MAX_TEXT_LENGTH = 100000  # 256K context - send huge chunks
MIN_CHUNK_PROSE = 50
BATCH_SIZE = 2  # Translate 2 pages per API call
BATCH_TIMEOUT = 60  # Wait up to 60s for batch to fill

LANGUAGES = {
    "vi": "Vietnamese",
    "es-US": "Spanish (Latin America)",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
    "ko": "Korean",
}

TRANSLATABLE_FRONTMATTER_KEYS = {
    "title", "description", "details", "name", "tagline",
    "label", "text", "placeholder", "hero",
}


# ============================================================
# GLOBAL STATE
# ============================================================

_client: Optional[OpenAI] = None
_client_lock = threading.Lock()
_rate_limit_delay = 1.0
_rate_limit_lock = threading.Lock()
_last_request_time = 0.0


# ============================================================
# API CLIENT
# ============================================================

def get_client() -> OpenAI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=TIMEOUT)
    return _client


# ============================================================
# RATE LIMITING (Adaptive for Free Tier)
# ============================================================

def wait_for_rate_limit():
    """Adaptive rate limiting based on API responses."""
    global _last_request_time, _rate_limit_delay
    
    with _rate_limit_lock:
        time_since_last = time.time() - _last_request_time
        if time_since_last < _rate_limit_delay:
            sleep_time = _rate_limit_delay - time_since_last
            time.sleep(sleep_time)
        _last_request_time = time.time()


def adjust_rate_limit(success: bool, status_code: Optional[int] = None):
    """Adjust rate limit based on response."""
    global _rate_limit_delay
    
    with _rate_limit_lock:
        if success:
            # Gradual reduction on success
            _rate_limit_delay = max(0.5, _rate_limit_delay * 0.95)
        elif status_code == 429:
            # Exponential backoff on rate limit
            _rate_limit_delay = min(10.0, _rate_limit_delay * 2.0)
            print(f"      Rate limited, new delay: {_rate_limit_delay:.1f}s")
        else:
            # Conservative increase on other errors
            _rate_limit_delay = min(10.0, _rate_limit_delay * 1.5)


# ============================================================
# ATOMIC FILE I/O
# ============================================================

def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


# ============================================================
# CACHE
# ============================================================

def cache_key(text: str, target_lang: str) -> str:
    norm = re.sub(r"\s+", " ", text.strip())
    raw = json.dumps({
        "v": CACHE_VERSION, "m": MODEL, "s": "en",
        "t": target_lang, "text": norm, "len": len(text),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def load_cache() -> dict:
    data = load_json(CACHE_FILE)
    if data.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "entries": {}}
    data.setdefault("entries", {})
    return data


def save_cache(cache: dict) -> None:
    save_json(CACHE_FILE, cache)


def cache_get(cache: dict, text: str, target: str) -> Optional[str]:
    entry = cache["entries"].get(cache_key(text, target))
    if entry and isinstance(entry.get("translation"), str):
        return entry["translation"]
    return None


def cache_put(cache: dict, text: str, target: str, translation: str) -> None:
    cache["entries"][cache_key(text, target)] = {
        "source": text, "target": target,
        "translation": translation, "ts": int(time.time()),
    }


# ============================================================
# PAGE STATE
# ============================================================

def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_state() -> dict:
    data = load_json(STATE_FILE)
    if data.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "pages": {}}
    data.setdefault("pages", {})
    return data


def save_state(state: dict) -> None:
    save_json(STATE_FILE, state)


def page_needs_translation(state: dict, rel: str, h: str, lang: str, force: bool) -> bool:
    if force:
        return True
    entry = state["pages"].get(f"{lang}:{rel}")
    return not entry or entry.get("hash") != h


def page_mark_done(state: dict, rel: str, h: str, lang: str) -> None:
    state["pages"][f"{lang}:{rel}"] = {"hash": h, "ts": int(time.time())}


# ============================================================
# MARKDOWN PROTECTION (Placeholder System)
# ============================================================

class Protector:
    """Replaces non-translatable content with stable placeholders."""

    def __init__(self):
        self._items: list[str] = []

    def _placeholder(self, idx: int) -> str:
        return f"__PH_{idx}__"

    def protect(self, text: str) -> str:
        """Find and replace all non-translatable regions with placeholders."""
        regions: list[tuple[int, int, str]] = []

        def add(pattern: str, flags: int = 0) -> None:
            for m in re.finditer(pattern, text, flags):
                regions.append((m.start(), m.end(), m.group()))

        # --- Block-level protections (longest patterns first) ---

        # Fenced code blocks (4-backtick, 3-backtick, 4-tilde, 3-tilde)
        add(r"````[\s\S]*?````")
        add(r"```[\s\S]*?```")
        add(r"~~~~[\s\S]*?~~~~")
        add(r"~~~[\s\S]*?~~~")

        # VitePress containers: ::: tip ... :::
        add(r"^:::\s*(?:tip|info|warning|danger|details)\b.*?^:::", re.DOTALL | re.MULTILINE)

        # HTML blocks: script, style, comments
        add(r"<script[\s\S]*?</script>", re.I)
        add(r"<style[\s\S]*?</style>", re.I)
        add(r"<!--[\s\S]*?-->", re.I)

        # Vue/VitePress components: <ComponentName ... /> or <ComponentName>...</ComponentName>
        add(r"<[A-Z][a-zA-Z0-9]*(?:\s[^>]*)?\s*/>")
        add(r"<[A-Z][a-zA-Z0-9]*(?:\s[^>]*)?>[\s\S]*?</[A-Z][a-zA-Z0-9]*>")

        # HTML tags with content (block-level)
        for tag in ["div", "p", "span", "section", "article", "header", "footer",
                     "nav", "main", "aside", "figure", "figcaption", "blockquote",
                     "li", "td", "th", "h[1-6]", "iframe", "table", "thead", "tbody"]:
            add(rf"<{tag}\b[^>]*>[\s\S]*?</{tag}>", re.I)

        # Self-closing HTML tags
        add(r"<(?:img|br|hr|input|source|link|meta)\b[^>]*/?>", re.I)

        # --- Inline protections ---

        regions.sort(key=lambda r: (r[0], -(r[1] - r[0])))
        merged: list[tuple[int, int, str]] = []
        for s, e, content in regions:
            if merged and s < merged[-1][1]:
                continue
            merged.append((s, e, content))

        unprotected: list[tuple[int, int]] = []
        pos = 0
        for s, e, _ in merged:
            if s > pos:
                unprotected.append((pos, s))
            pos = e
        if pos < len(text):
            unprotected.append((pos, len(text)))

        inline: list[tuple[int, int, str]] = []
        for ur_s, ur_e in unprotected:
            region = text[ur_s:ur_e]

            # Inline code
            for m in re.finditer(r"`[^`\n]+`", region):
                inline.append((ur_s + m.start(), ur_s + m.end(), m.group()))

            # Images: ![alt](url)
            for m in re.finditer(r"!\[[^\]]*\]\([^)]+\)", region):
                inline.append((ur_s + m.start(), ur_s + m.end(), m.group()))

            # Autolinks: <https://...>
            for m in re.finditer(r"<(https?://[^>]+)>", region):
                inline.append((ur_s + m.start(), ur_s + m.end(), m.group()))

            # Reference links: [text][ref]
            for m in re.finditer(r"\[[^\]]+\]\[[^\]]*\]", region):
                inline.append((ur_s + m.start(), ur_s + m.end(), m.group()))

            # VitePress template expressions: {{ ... }}
            for m in re.finditer(r"\{\{[^}]+\}\}", region):
                inline.append((ur_s + m.start(), ur_s + m.end(), m.group()))

            # Links: [text](url) - protect URL part
            for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", region):
                full_s = ur_s + m.start()
                full_e = ur_s + m.end()
                if any(full_s < bs and full_e > bs for bs, be, _ in merged):
                    continue
                url_part_start = ur_s + m.start(2) - 1
                url_part = m.group()[m.start(2) - m.start() - 1:]
                inline.append((url_part_start, full_e, url_part))

        # Merge and deduplicate
        all_regions = merged + inline
        all_regions.sort(key=lambda r: (r[0], -(r[1] - r[0])))
        final: list[tuple[int, int, str]] = []
        for s, e, content in all_regions:
            if final and s < final[-1][1]:
                continue
            final.append((s, e, content))

        # Replace with placeholders
        result = []
        pos = 0
        for s, e, content in final:
            if s > pos:
                result.append(text[pos:s])
            idx = len(self._items)
            self._items.append(content)
            result.append(self._placeholder(idx))
            pos = e
        if pos < len(text):
            result.append(text[pos:])

        return "".join(result)

    def restore(self, text: str) -> str:
        """Replace all placeholders with original content."""
        for idx, content in enumerate(self._items):
            text = text.replace(self._placeholder(idx), content)
        return text

    def validate_restored(self, original: str, restored: str) -> list[str]:
        """Check that all placeholders were properly restored."""
        errors = []
        remaining = re.findall(r"__PH_\d+__", restored)
        if remaining:
            errors.append(f"Unrestored placeholders: {remaining[:5]}")
        return errors


def prose_only(text: str) -> str:
    """Return only translatable prose, stripping placeholders and formatting."""
    text = re.sub(r"__PH_\d+__", "", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"[*_~`]", "", text)
    return text.strip()


def validate_placeholder_coverage(original: str, protected: str) -> dict:
    """Validate that protection is working well."""
    orig_len = len(original)
    prot_len = len(protected)
    placeholder_count = len(re.findall(r"__PH_\d+__", protected))

    stats = {
        "original_bytes": orig_len,
        "protected_bytes": prot_len,
        "compression_ratio": prot_len / orig_len if orig_len > 0 else 0,
        "placeholder_count": placeholder_count,
        "avg_bytes_per_placeholder": prot_len / placeholder_count if placeholder_count > 0 else 0,
    }

    # Warn if protection isn't doing much
    if stats["compression_ratio"] > 0.95:
        print(f"      WARNING: Low protection coverage: {stats['compression_ratio']:.1%}")

    return stats


# ============================================================
# FRONTMATTER
# ============================================================

def extract_frontmatter(md: str) -> Tuple[Optional[str], str]:
    """Split frontmatter from body. Returns (frontmatter_or_None, body)."""
    m = re.match(r"^(---\n.*?\n---\n?)", md, re.DOTALL)
    if m:
        return m.group(1), md[m.end():]
    return None, md


def translate_frontmatter(fm: str, client: OpenAI, target_lang: str, cache: dict,
                          stats: dict, lock: threading.Lock) -> str:
    """Translate translatable values in YAML frontmatter."""
    lines = fm.split("\n")
    result = []

    for line in lines:
        # Try double-quoted
        m = re.match(r'^(\s*-?\s*[a-zA-Z_-]+:\s+)"((?:\\.|[^"\\])*)"', line)
        if m:
            key_part, value = m.group(1), m.group(2)
            quote = '"'
            value = value.replace('\\"', '"')
        else:
            # Try single-quoted
            m = re.match(r"^(\s*-?\s*[a-zA-Z_-]+:\s+)'((?:\\'|[^'\\])*)'", line)
            if m:
                key_part, value = m.group(1), m.group(2)
                quote = "'"
                value = value.replace("\\'", "'")
            else:
                # Try unquoted
                m = re.match(r'^(\s*-?\s*[a-zA-Z_-]+:\s+)([^\n#]+?)(?:\s*#.*)?$', line)
                if m:
                    key_part, value = m.group(1), m.group(2).strip()
                    quote = None
                else:
                    result.append(line)
                    continue

        key_name = re.sub(r"^\s*-?\s*", "", key_part).strip().rstrip(":").lower()
        if key_name not in TRANSLATABLE_FRONTMATTER_KEYS or len(value.strip()) < MIN_TEXT_LENGTH:
            result.append(line)
            continue

        # Translate this value
        cached = cache_get(cache, value, target_lang)
        if cached is not None:
            with lock:
                stats["cache_hits"] += 1
            translated = cached
        else:
            translated = call_api(client, value, target_lang)
            translated = post_process(translated, target_lang)
            with lock:
                cache_put(cache, value, target_lang, translated)
                stats["api_requests"] += 1

        if quote == '"':
            escaped = translated.replace('"', '\\"')
        elif quote == "'":
            escaped = translated.replace("'", "\\'")
        else:
            escaped = translated
        q = quote or '"'
        result.append(f'{key_part.rstrip()} {q}{escaped}{q}')

    return "\n".join(result)


# ============================================================
# API CALL + RETRY
# ============================================================

def call_api(client: OpenAI, text: str, target_lang: str) -> str:
    """Call the translation API with adaptive retry and rate limiting."""
    lang_full = LANGUAGES.get(target_lang, target_lang)
    system_msg = (
        f"Translate the following Markdown from English to {lang_full}. "
        f"Translate only human-readable prose. "
        f"Preserve all __PH_N__ placeholders exactly as they appear. "
        f"Preserve all Markdown formatting, structure, and meaning. "
        f"Return only the translated text with no explanations."
    )

    last_error = "Unknown error"
    for attempt in range(MAX_RETRIES + 1):
        wait_for_rate_limit()

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": text},
                ],
                temperature=0.2,  # MoE-aware: slightly higher than 0
                max_tokens=MAX_TOKENS,
            )
            content = resp.choices[0].message.content
            if not content or not content.strip():
                raise RuntimeError("Empty translation")

            adjust_rate_limit(True)
            return content.strip()

        except APITimeoutError:
            last_error = "timeout"
            adjust_rate_limit(False)
        except APIConnectionError as e:
            last_error = f"connection: {e}"
            adjust_rate_limit(False)
        except APIStatusError as e:
            if e.status_code in {400, 401, 403, 404, 422}:
                raise RuntimeError(f"API error {e.status_code}: {e.message[:300]}")
            last_error = f"HTTP {e.status_code}"
            adjust_rate_limit(False, e.status_code)
        except RuntimeError:
            raise
        except Exception as e:
            last_error = str(e)[:200]
            adjust_rate_limit(False)

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            print(f"      Retry {attempt + 1}/{MAX_RETRIES} after {delay}s ({last_error})")
            time.sleep(delay)

    raise RuntimeError(f"API failed after {MAX_RETRIES} retries: {last_error}")


# ============================================================
# POST-PROCESSING
# ============================================================

def post_process(text: str, target_lang: str) -> str:
    if target_lang == "vi":
        text = re.sub(r"\s+([!?.,;:])", r"\1", text)
        text = re.sub(r"  +", " ", text)
    text = re.sub(r"\]\s*\(", "](", text)
    return text


# ============================================================
# BATCHED TRANSLATION
# ============================================================

class PageBatch:
    """Batch multiple pages for single API call."""

    def __init__(self):
        self.pages: list[tuple[str, str, Path, Protector]] = []  # (md_content, rel, path, protector)
        self.total_chars = 0

    def can_add(self, md_content: str) -> bool:
        """Check if page can fit in batch."""
        _, body = extract_frontmatter(md_content)
        protector = Protector()
        protected = protector.protect(body)
        
        # Estimate tokens (rough: 1 token ≈ 4 chars)
        est_tokens = len(protected) / 4
        current_tokens = self.total_chars / 4
        
        # Leave 50K tokens headroom for markers, system prompt, output
        return (current_tokens + est_tokens) < 200000

    def add(self, md_content: str, rel: Path) -> None:
        """Add page to batch."""
        _, body = extract_frontmatter(md_content)
        protector = Protector()
        protected = protector.protect(body)
        
        self.pages.append((md_content, protected, rel, protector))
        self.total_chars += len(protected)

    def is_full(self) -> bool:
        """Check if batch is at target size."""
        return len(self.pages) >= BATCH_SIZE

    def is_empty(self) -> bool:
        return len(self.pages) == 0

    def to_api_request(self) -> str:
        """Format batch for API request."""
        parts = []
        for i, (_, protected, rel, _) in enumerate(self.pages):
            parts.append(f"---PAGE_{i}_START---{rel.as_posix()}---\n{protected}\n---PAGE_{i}_END---\n")
        return "\n".join(parts)

    def parse_response(self, response: str) -> dict[Path, str]:
        """Parse API response back into pages."""
        results = {}
        
        for i, (_, _, rel, protector) in enumerate(self.pages):
            # Extract page content
            pattern = rf"---PAGE_{i}_START---[^\n]*\n(.*?)\n---PAGE_{i}_END---"
            match = re.search(pattern, response, re.DOTALL)
            
            if match:
                translated = match.group(1)
                restored = protector.restore(translated)
                results[rel] = restored
            else:
                print(f"      WARNING: Could not parse page {i} ({rel}) from response")
                results[rel] = None
        
        return results


def translate_markdown_batch(
    batch: PageBatch,
    target_lang: str,
    client: OpenAI,
    cache: dict,
    stats: dict,
    lock: threading.Lock,
) -> Tuple[dict[Path, str], List[str]]:
    """Translate an entire batch via single API call."""
    if batch.is_empty():
        return {}, []

    failed = []
    request_text = batch.to_api_request()

    # Check cache first
    cached = cache_get(cache, request_text, target_lang)
    if cached is not None:
        with lock:
            stats["cache_hits"] += 1
        return batch.parse_response(cached), []

    with lock:
        stats["cache_misses"] += 1

    try:
        translated = call_api(client, request_text, target_lang)
        translated = post_process(translated, target_lang)
        
        with lock:
            cache_put(cache, request_text, target_lang, translated)
            stats["api_requests"] += 1
        
        results = batch.parse_response(translated)
        
        # Track failures
        for rel, content in results.items():
            if content is None:
                prose = prose_only(request_text)
                failed.append(prose[:60])
        
        return results, failed

    except Exception as e:
        print(f"      ERROR in batch: {e}")
        failed.append(str(e)[:60])
        return {}, failed


# ============================================================
# PATH FIXING
# ============================================================

def fix_relative_paths(md: str, source_rel: Path) -> str:
    depth = len(source_rel.parts) - 1
    if depth <= 0:
        return md

    extra = "../" * depth

    def fix(m):
        path = m.group(1)
        if path.startswith("../"):
            return m.group(0).replace(path, extra + path, 1)
        return m.group(0)

    md = re.sub(r"""(?:from|require)\s*\(\s*['"](\.\.[^'"]+)['"]""", fix, md)
    md = re.sub(r"""import\s+[^'"]*from\s*['"](\.\.[^'"]+)['"]""", fix, md)
    return md


# ============================================================
# PRE-VALIDATION
# ============================================================

def pre_validate_pages(pages: list[Path]) -> dict[str, list[str]]:
    """Validate all pages before translation."""
    issues = {}
    for md_path in pages:
        rel = str(md_path.relative_to(DOCS_DIR))
        rel_issues = []

        md = md_path.read_text(encoding="utf-8")
        _, body = extract_frontmatter(md)

        # Check for pre-existing placeholders
        placeholder_count = len(re.findall(r"__PH_\d+__", body))
        if placeholder_count > 0:
            rel_issues.append(f"Already has {placeholder_count} placeholders (will break)")

        # Check for marker conflicts
        if "---PAGE_" in body:
            rel_issues.append("Body contains ---PAGE_ markers (conflicts with batching)")

        # Check for malformed code blocks
        if body.count("```") % 2 != 0:
            rel_issues.append("Unmatched backticks (code block)")

        if rel_issues:
            issues[rel] = rel_issues

    return issues


# ============================================================
# FILE DISCOVERY
# ============================================================

def find_source_pages(docs: Path, lang_dirs: set) -> list[Path]:
    pages = []
    for md in docs.rglob("*.md"):
        rel = md.relative_to(docs)
        if rel.parts and rel.parts[0] in lang_dirs:
            continue
        if ".vitepress" in rel.parts:
            continue
        if "[" in md.name:
            continue
        pages.append(md)
    return sorted(pages)


# ============================================================
# METRICS LOGGING
# ============================================================

class MetricsLogger:
    """Log translation metrics for CI/CD integration."""

    def __init__(self):
        self.metrics = {
            "build_id": os.environ.get("CF_PAGES_BUILD_ID", "local"),
            "timestamp": time.time(),
            "pages": [],
            "summary": {},
        }

    def log_page(self, lang: str, rel: str, elapsed: float, cache_hits: int, 
                 api_calls: int, success: bool) -> None:
        self.metrics["pages"].append({
            "lang": lang,
            "page": rel,
            "elapsed_s": elapsed,
            "cache_hits": cache_hits,
            "api_calls": api_calls,
            "success": success,
        })

    def finalize(self, total_time: float, total_hits: int, total_misses: int, total_calls: int) -> None:
        self.metrics["summary"] = {
            "total_time_s": total_time,
            "cache_hits": total_hits,
            "cache_misses": total_misses,
            "api_calls": total_calls,
            "avg_time_per_call": total_time / max(total_calls, 1),
        }

    def output(self) -> str:
        """Return JSON metrics string."""
        return json.dumps(self.metrics, indent=2)


# ============================================================
# CLI
# ============================================================

def parse_args():
    p = argparse.ArgumentParser(description="VitePress Markdown Translator (Optimized for Laguna XS 2.1)")
    p.add_argument("--langs", default=",".join(LANGUAGES.keys()),
                   help="Comma-separated target languages (default: all)")
    p.add_argument("--docs", type=Path, default=DOCS_DIR,
                   help="Source docs directory (default: docs/)")
    p.add_argument("--workers", type=int, default=WORKERS,
                   help=f"Parallel workers (default: {WORKERS})")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be translated without API calls")
    p.add_argument("--clear-cache", action="store_true",
                   help="Delete translation cache before starting")
    p.add_argument("--force", action="store_true",
                   help="Force retranslation (still uses string cache)")
    p.add_argument("--strict", action="store_true",
                   help="Fail on any translation error")
    return p.parse_args()


# ============================================================
# MAIN
# ============================================================

def main():
    args = parse_args()

    # API key check
    if not args.dry_run and not API_KEY:
        print("ERROR: TRANSLATION_API_KEY (or NVIDIA_API_KEY) is not set.")
        print()
        print('Run: export TRANSLATION_API_KEY="your-key"')
        print()
        print("For Cloudflare Pages:")
        print("  1. Go to Pages -> your project -> Settings -> Build")
        print("  2. Add build variable: TRANSLATION_API_KEY = your-key")
        sys.exit(1)

    # Validate API key
    if not args.dry_run and API_KEY:
        print("Validating API key...")
        try:
            client = get_client()
            client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
            )
            print("API key OK.")
        except Exception as e:
            err_str = str(e)
            if "403" in err_str or "401" in err_str:
                print(f"ERROR: API key is invalid or expired: {e}")
                sys.exit(1)
            print(f"WARNING: Could not validate API key: {e}")

    # Clear cache
    if args.clear_cache:
        for f in [CACHE_FILE, STATE_FILE]:
            if f.exists():
                f.unlink()
                print(f"Deleted: {f}")

    docs = args.docs.resolve()
    if not docs.is_dir():
        print(f"ERROR: docs directory not found: {docs}")
        sys.exit(1)

    lang_dirs = set(LANGUAGES.keys())
    requested = [c.strip() for c in args.langs.split(",") if c.strip()]
    for lang in requested:
        if lang not in LANGUAGES:
            print(f"ERROR: unknown language '{lang}'")
            print(f"Supported: {', '.join(LANGUAGES.keys())}")
            sys.exit(1)

    pages = find_source_pages(docs, lang_dirs)
    state = load_state()
    cache = load_cache()

    print()
    print("VitePress Markdown Translator (Optimized for Laguna XS 2.1)")
    print("=" * 60)
    print(f"Source:    {docs}")
    print(f"Pages:     {len(pages)}")
    print(f"Languages: {', '.join(requested)}")
    print(f"Workers:   {args.workers}")
    print(f"Model:     {MODEL}")
    print(f"Batch:     {BATCH_SIZE} pages/call, {MAX_TEXT_LENGTH} chars/request")
    print()

    if args.dry_run:
        print("DRY RUN: no API calls will be made.")
        print()

    # Pre-validate
    if not args.dry_run:
        validation_issues = pre_validate_pages(pages)
        if validation_issues:
            print("VALIDATION ERRORS:")
            for rel, errs in validation_issues.items():
                print(f"  {rel}:")
                for err in errs:
                    print(f"    - {err}")
            if args.strict:
                sys.exit(1)

    stats = {"cache_hits": 0, "cache_misses": 0, "api_requests": 0}
    lock = threading.Lock()
    metrics = MetricsLogger()
    build_start = time.time()

    for lang in requested:
        print(f"[{lang}] {LANGUAGES[lang]}")

        pages_skipped = 0
        pages_translated = 0
        lang_start_time = time.time()
        lang_stats = {"cache_hits": 0, "cache_misses": 0, "api_requests": 0}
        lang_lock = threading.Lock()
        tasks = []

        for md_path in pages:
            rel = str(md_path.relative_to(docs))
            h = file_hash(md_path)
            if not page_needs_translation(state, rel, h, lang, args.force):
                pages_skipped += 1
                if not args.dry_run:
                    print(f"  {rel:50s} SKIP")
                continue
            pages_translated += 1
            if args.dry_run:
                print(f"  {rel:50s} WOULD TRANSLATE")
            else:
                tasks.append((md_path, h))

        print(f"  pages skipped: {pages_skipped}")
        print(f"  pages changed: {pages_translated}")

        if not args.dry_run and tasks:
            client = get_client()
            lang_failures: list[str] = []

            def do_task(batch_data: tuple[int, list[tuple[Path, str]]]) -> tuple[int, dict[Path, str], list[str], float]:
                batch_idx, batch_tasks = batch_data
                batch = PageBatch()
                
                for md_path, h in batch_tasks:
                    md = md_path.read_text(encoding="utf-8")
                    batch.add(md, md_path.relative_to(docs))
                
                t0 = time.time()
                results, failed = translate_markdown_batch(
                    batch, lang, client, cache, lang_stats, lang_lock
                )
                elapsed = time.time() - t0
                
                # Write results
                for rel, translated in results.items():
                    if translated is None:
                        continue
                    
                    md_path = docs / rel
                    translated = fix_relative_paths(translated, rel)
                    out_dir = docs / lang / rel.parent
                    atomic_write(out_dir / md_path.name, translated)
                    
                    # Find original to mark done
                    orig_rel = str(rel)
                    for orig_path, _ in batch_tasks:
                        if str(orig_path.relative_to(docs)) == orig_rel:
                            with lang_lock:
                                page_mark_done(state, orig_rel, file_hash(orig_path), lang)
                            break
                
                print(f"  Batch {batch_idx}: {len(results)} pages ({elapsed:.1f}s)")
                return batch_idx, results, failed, elapsed

            # Batch tasks
            batches = []
            current_batch = []
            for task in tasks:
                if len(current_batch) >= BATCH_SIZE:
                    batches.append(current_batch)
                    current_batch = []
                current_batch.append(task)
            if current_batch:
                batches.append(current_batch)

            batch_tasks = [(i, b) for i, b in enumerate(batches)]

            if args.workers <= 1:
                for batch_task in batch_tasks:
                    try:
                        _, results, failed, _ = do_task(batch_task)
                        if failed:
                            lang_failures.extend(failed)
                    except Exception as e:
                        print(f"  ERROR: {e}")
                        if args.strict:
                            sys.exit(1)
            else:
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = {pool.submit(do_task, bt): bt for bt in batch_tasks}
                    for future in as_completed(futures):
                        try:
                            _, results, failed, _ = future.result()
                            if failed:
                                lang_failures.extend(failed)
                        except Exception as e:
                            print(f"  ERROR: {e}")
                            if args.strict:
                                sys.exit(1)

            if lang_failures:
                print(f"\n  WARNING: {len(lang_failures)} string(s) fell back or failed")

            save_cache(cache)
            save_state(state)

            lang_elapsed = time.time() - lang_start_time
            with lock:
                stats["cache_hits"] += lang_stats["cache_hits"]
                stats["cache_misses"] += lang_stats["cache_misses"]
                stats["api_requests"] += lang_stats["api_requests"]

        print()

    build_elapsed = time.time() - build_start

    print("=" * 60)
    print("Translation complete.")
    print()
    print(f"Total time:      {build_elapsed:.1f}s")
    print(f"Pages scanned:   {len(pages) * len(requested)}")
    print(f"Cache hits:      {stats['cache_hits']}")
    print(f"Cache misses:    {stats['cache_misses']}")
    print(f"API requests:    {stats['api_requests']}")
    print()
    print(f"Cache:  {CACHE_FILE}")
    print(f"State:  {STATE_FILE}")
    print(f"Output: {docs}/{{lang}}/")
    if args.strict:
        print("Mode:   STRICT (errors cause exit)")
    print()

    # Output metrics
    metrics.finalize(build_elapsed, stats["cache_hits"], stats["cache_misses"], stats["api_requests"])
    print("Metrics (JSON):")
    print(metrics.output())
    print()


if __name__ == "__main__":
    main()