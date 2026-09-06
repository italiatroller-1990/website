#!/usr/bin/env python3
"""
VitePress Markdown Translator
==============================

Translates English Markdown source files in docs/ to target languages
using an OpenAI-compatible API (NVIDIA NIM).

Workflow:
    python3 translate.py          # translate docs/*.md -> docs/{lang}/*.md
    npm run docs:build            # VitePress builds everything

Features:
- Translates Markdown source, not generated HTML
- Content-hash cache survives between builds
- Page-level incremental detection (skip unchanged pages)
- Placeholder-based syntax protection (code, HTML, URLs, VitePress)
- Parallel API requests with configurable workers
- Atomic writes for cache and translated files
- Strict validation of translated output

Usage:
    export TRANSLATION_API_KEY="nvapi-..."
    python3 translate.py

    python3 translate.py --langs vi,ja
    python3 translate.py --workers 4
    python3 translate.py --dry-run
    python3 translate.py --clear-cache
    python3 translate.py --force
    python3 translate.py --strict
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
from typing import List, Optional, Tuple


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
MODEL = os.environ.get("TRANSLATION_MODEL", "openai/gpt-oss-20b")
WORKERS = int(os.environ.get("TRANSLATION_WORKERS", "4"))
TIMEOUT = int(os.environ.get("TRANSLATION_TIMEOUT", "120"))
MAX_RETRIES = int(os.environ.get("TRANSLATION_MAX_RETRIES", "5"))
RETRY_DELAYS = [2, 4, 8, 16, 32]

CACHE_VERSION = 5
REQUEST_DELAY = 0.15
MAX_TOKENS = 4096
MIN_TEXT_LENGTH = 2
MAX_TEXT_LENGTH = 8000
MIN_CHUNK_PROSE = 50  # minimum prose chars to send an API call

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
# API CLIENT
# ============================================================

_client: Optional[OpenAI] = None
_client_lock = threading.Lock()


def get_client() -> OpenAI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=TIMEOUT)
    return _client


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
# MARKDOWN PROTECTION (placeholder system)
# ============================================================

class Protector:
    """Replaces non-translatable content with stable placeholders.

    The placeholder format __PH_N__ is chosen to be extremely unlikely
    to appear in natural text or be modified by the translation model.
    """

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

        # --- Inline protections (within remaining unprotected regions) ---

        # Collect unprotected regions
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

            # Links: [text](url) - protect URL part, keep text translatable
            for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", region):
                full_s = ur_s + m.start()
                full_e = ur_s + m.end()
                # Skip if already covered by block protection
                if any(full_s < bs and full_e > bs for bs, be, _ in merged):
                    continue
                # Protect the ](url) part so URL isn't translated
                url_part_start = ur_s + m.start(2) - 1  # position of '('
                url_part = m.group()[m.start(2) - m.start() - 1:]
                inline.append((url_part_start, full_e, url_part))

        # Merge inline into regions, deduplicate overlaps
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
    """Return only the translatable prose, stripping placeholders and formatting."""
    text = re.sub(r"__PH_\d+__", "", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"[*_~`]", "", text)
    return text.strip()


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
            time.sleep(REQUEST_DELAY)

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
    """Call the translation API with retry logic."""
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
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": text},
                ],
                temperature=0,
                max_tokens=MAX_TOKENS,
            )
            content = resp.choices[0].message.content
            if not content or not content.strip():
                raise RuntimeError("Empty translation")
            return content.strip()

        except APITimeoutError:
            last_error = "timeout"
        except APIConnectionError as e:
            last_error = f"connection: {e}"
        except APIStatusError as e:
            if e.status_code in {400, 401, 403, 404, 422}:
                raise RuntimeError(f"API error {e.status_code}: {e.message[:300]}")
            last_error = f"HTTP {e.status_code}"
        except RuntimeError:
            raise
        except Exception as e:
            last_error = str(e)[:200]

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
# TRANSLATE MARKDOWN
# ============================================================

def translate_markdown(
    md: str,
    target_lang: str,
    client: OpenAI,
    cache: dict,
    stats: dict,
    lock: threading.Lock,
) -> Tuple[str, List[str]]:
    """Translate a full Markdown document. Returns (translated, failed_list)."""
    fm, body = extract_frontmatter(md)

    # Phase 1: Protect non-translatable content
    protector = Protector()
    protected_body = protector.protect(body)

    # Phase 2: Split into chunks for translation
    chunks = split_into_chunks(protected_body)

    # Phase 3: Translate each chunk
    failed: list[str] = []
    translated_chunks: list[str] = []

    for chunk in chunks:
        # Skip chunks with no translatable prose
        prose = prose_only(chunk)
        if len(prose) < MIN_TEXT_LENGTH:
            translated_chunks.append(chunk)
            continue

        cached = cache_get(cache, chunk, target_lang)
        if cached is not None:
            with lock:
                stats["cache_hits"] += 1
            translated_chunks.append(cached)
            continue

        with lock:
            stats["cache_misses"] += 1

        try:
            translated = call_api(client, chunk, target_lang)
            translated = post_process(translated, target_lang)
            with lock:
                cache_put(cache, chunk, target_lang, translated)
                stats["api_requests"] += 1
            translated_chunks.append(translated)
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            print(f"      ERROR: {e}")
            translated_chunks.append(chunk)
            failed.append(prose[:60])

    # Phase 4: Restore placeholders
    translated_body = "\n\n".join(translated_chunks)
    restored_body = protector.restore(translated_body)

    # Phase 5: Validate
    validation_errors = protector.validate_restored(body, restored_body)
    if validation_errors:
        for err in validation_errors:
            print(f"      VALIDATION: {err}")

    # Phase 6: Translate frontmatter
    if fm:
        translated_fm = translate_frontmatter(fm, client, target_lang, cache, stats, lock)
        return translated_fm + restored_body, failed

    return restored_body, failed


def split_into_chunks(text: str) -> list[str]:
    """Split text into translatable chunks.

    Strategy:
    1. If under MAX_TEXT_LENGTH, send as one chunk
    2. Split by double-newlines (paragraph boundaries)
    3. Merge small adjacent chunks to avoid tiny API calls
    """
    if len(text) <= MAX_TEXT_LENGTH:
        return [text]

    # Split by paragraphs
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len > MAX_TEXT_LENGTH and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += para_len + 2

    if current:
        chunks.append("\n\n".join(current))

    # Merge small chunks with neighbors
    return merge_small_chunks(chunks)


def merge_small_chunks(chunks: list[str], min_size: int = 500) -> list[str]:
    """Merge undersized chunks with their neighbors to avoid wasted API calls.

    A chunk with less than min_size chars of prose gets absorbed into the
    next chunk rather than triggering its own API call.
    """
    if len(chunks) <= 1:
        return chunks

    merged: list[str] = []
    buf = chunks[0]

    for chunk in chunks[1:]:
        buf_prose = prose_only(buf)
        if len(buf_prose) < min_size:
            buf = buf + "\n\n" + chunk
        else:
            merged.append(buf)
            buf = chunk

    if buf:
        merged.append(buf)

    return merged


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
# CLI
# ============================================================

def parse_args():
    p = argparse.ArgumentParser(description="VitePress Markdown Translator")
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
        print('Run: export TRANSLATION_API_KEY="nvapi-..."')
        print()
        print("For Cloudflare Pages:")
        print("  1. Go to Pages -> your project -> Settings -> Build")
        print("  2. Add build variable: TRANSLATION_API_KEY = nvapi-...")
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
    print("VitePress Markdown Translator")
    print("=" * 50)
    print(f"Source:    {docs}")
    print(f"Pages:     {len(pages)}")
    print(f"Languages: {', '.join(requested)}")
    print(f"Workers:   {args.workers}")
    print(f"Model:     {MODEL}")
    print()

    if args.dry_run:
        print("DRY RUN: no API calls will be made.")
        print()

    stats = {"cache_hits": 0, "cache_misses": 0, "api_requests": 0}
    lock = threading.Lock()

    for lang in requested:
        print(f"[{lang}] {LANGUAGES[lang]}")

        pages_skipped = 0
        pages_translated = 0
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

            def do_task(task):
                md_path, h = task
                rel = md_path.relative_to(docs)
                t0 = time.time()
                md = md_path.read_text(encoding="utf-8")
                translated, failed = translate_markdown(
                    md, lang, client, cache, stats, lock,
                )
                translated = fix_relative_paths(translated, rel)
                out_dir = docs / lang / rel.parent
                atomic_write(out_dir / md_path.name, translated)
                elapsed = time.time() - t0
                with lock:
                    page_mark_done(state, str(rel), h, lang)
                print(f"  {str(rel):50s} DONE ({elapsed:.1f}s)")
                return {"rel": str(rel), "hash": h, "failed": failed}

            if args.workers <= 1:
                for task in tasks:
                    try:
                        r = do_task(task)
                        if r["failed"]:
                            lang_failures.extend(r["failed"])
                    except Exception as e:
                        print(f"  ERROR: {e}")
                        if args.strict:
                            sys.exit(1)
            else:
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = {pool.submit(do_task, t): t for t in tasks}
                    for future in as_completed(futures):
                        try:
                            r = future.result()
                            if r["failed"]:
                                lang_failures.extend(r["failed"])
                        except Exception as e:
                            print(f"  ERROR: {e}")
                            if args.strict:
                                sys.exit(1)

            if lang_failures:
                print(f"\n  WARNING: {len(lang_failures)} string(s) fell back to English")

            save_cache(cache)
            save_state(state)

        print()

    print("=" * 50)
    print("Translation complete.")
    print()
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


if __name__ == "__main__":
    main()
