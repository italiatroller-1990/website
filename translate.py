#!/usr/bin/env python3
"""
VitePress Markdown Translator
==============================

Translates English Markdown source files in docs/ to target languages
using NVIDIA NIM (Riva Translate 4B Instruct v2).

Workflow:

    python3 translate.py          # translate docs/*.md → docs/{lang}/*.md
    npm run docs:build            # VitePress builds everything

The script NEVER touches .vitepress/dist/.

Features:
- Translates Markdown source, not generated HTML
- Content-hash cache (SHA-256) survives between builds
- Page-level incremental detection (skip unchanged pages)
- Markdown-aware: protects code, links, URLs, frontmatter, VitePress syntax
- Parallel NVIDIA requests with ThreadPoolExecutor
- Atomic writes (temp + rename) for cache and translated files
- Zero unnecessary NVIDIA requests

Usage:

    export NVIDIA_API_KEY="nvapi-..."
    python3 translate.py

    python3 translate.py --langs vi,ja
    python3 translate.py --workers 4
    python3 translate.py --dry-run
    python3 translate.py --clear-cache
    python3 translate.py --force
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
from typing import Dict, List, Optional, Tuple

def ensure_requirements():
    """Install requirements.txt if requests is missing."""
    try:
        import requests
    except ImportError:
        print("Installing requirements...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests"])
        print()

ensure_requirements()

import requests


# ============================================================
# CONFIGURATION
# ============================================================

DOCS_DIR = Path("docs")

CACHE_FILE = DOCS_DIR / ".vitepress" / "translation-cache.json"
STATE_FILE = DOCS_DIR / ".vitepress" / "translation-state.json"

NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = "nvidia/riva-translate-4b-instruct-v2"

API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()

CACHE_VERSION = 1

# Languages
LANGUAGES = {
    "vi": "Vietnamese",
    "es-US": "Spanish (Latin America)",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
    "ko": "Korean",
}

# NVIDIA prompt codes
LANG_PROMPT = {
    "vi": "vi",
    "es-US": "es-us",
    "fr": "fr",
    "de": "de",
    "ja": "ja",
    "ko": "ko",
}

# Request settings
REQUEST_TIMEOUT = 120
MAX_RETRIES = 5
RETRY_DELAYS = [2, 4, 8, 16, 32]
REQUEST_DELAY = 0.20
MAX_TOKENS = 4096

# Text settings
MIN_TEXT_LENGTH = 2
MAX_TEXT_LENGTH = 6000


# ============================================================
# ATOMIC FILE I/O
# ============================================================

def atomic_write(path: Path, content: str) -> None:
    """Write content atomically via temp file + rename."""
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
    """Load JSON file, return empty dict on error."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_json(path: Path, data: dict) -> None:
    """Save JSON atomically."""
    content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write(path, content)


# ============================================================
# TRANSLATION CACHE
# ============================================================

def cache_key(text: str, target_lang: str) -> str:
    """SHA-256 key from version + model + source + target + normalized text."""
    norm = re.sub(r"\s+", " ", text.strip())
    raw = json.dumps({
        "v": CACHE_VERSION,
        "m": NIM_MODEL,
        "s": "en",
        "t": target_lang,
        "text": norm,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cache() -> dict:
    data = load_json(CACHE_FILE)
    if data.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "entries": {}}
    if "entries" not in data:
        data["entries"] = {}
    return data


def save_cache(cache: dict) -> None:
    save_json(CACHE_FILE, cache)


def cache_get(cache: dict, text: str, target: str) -> Optional[str]:
    key = cache_key(text, target)
    entry = cache["entries"].get(key)
    if entry and isinstance(entry.get("translation"), str):
        return entry["translation"]
    return None


def cache_put(cache: dict, text: str, target: str, translation: str) -> None:
    key = cache_key(text, target)
    cache["entries"][key] = {
        "source": text,
        "target": target,
        "translation": translation,
        "ts": int(time.time()),
    }


# ============================================================
# PAGE STATE (incremental detection)
# ============================================================

def file_hash(path: Path) -> str:
    """SHA-256 hash of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_state() -> dict:
    data = load_json(STATE_FILE)
    if data.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "pages": {}}
    if "pages" not in data:
        data["pages"] = {}
    return data


def save_state(state: dict) -> None:
    save_json(STATE_FILE, state)


def page_needs_translation(state: dict, rel_path: str, source_hash: str, lang: str, force: bool) -> bool:
    """Check if a page needs translation for a given language."""
    if force:
        return True
    key = f"{lang}:{rel_path}"
    entry = state["pages"].get(key)
    if not entry:
        return True
    return entry.get("hash") != source_hash


def page_mark_done(state: dict, rel_path: str, source_hash: str, lang: str) -> None:
    key = f"{lang}:{rel_path}"
    state["pages"][key] = {"hash": source_hash, "ts": int(time.time())}


# ============================================================
# NVIDIA NIM API
# ============================================================

def nim_translate(text: str, target_lang: str, api_key: str) -> str:
    """Translate one text unit via NVIDIA NIM chat completions."""
    prompt_code = LANG_PROMPT.get(target_lang, target_lang.lower())

    payload = {
        "model": NIM_MODEL,
        "messages": [
            {"role": "system", "content": f"en-{prompt_code}"},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = "Unknown error"

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(
                NIM_ENDPOINT, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )

            if resp.ok:
                data = resp.json()
                translated = data["choices"][0]["message"]["content"]
                if not isinstance(translated, str) or not translated.strip():
                    raise RuntimeError("Empty translation from NVIDIA")
                return translated.strip()

            # Permanent errors
            if resp.status_code in {400, 401, 403, 404, 422}:
                raise RuntimeError(
                    f"NVIDIA HTTP {resp.status_code}: {resp.text[:500]}"
                )

            # Transient errors
            if resp.status_code in {429, 500, 502, 503, 504}:
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                if attempt < MAX_RETRIES:
                    # Use Retry-After header if present (common for 429)
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        delay = int(retry_after)
                    else:
                        delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    print(f"      Retry {attempt + 1}/{MAX_RETRIES} after {delay}s (HTTP {resp.status_code})")
                    time.sleep(delay)
                    continue
                break

            last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            break

        except requests.exceptions.Timeout:
            last_error = "Request timed out"
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                print(f"      Retry {attempt + 1}/{MAX_RETRIES} after {delay}s (timeout)")
                time.sleep(delay)
                continue
            break
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {e}"
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                print(f"      Retry {attempt + 1}/{MAX_RETRIES} after {delay}s (connection error)")
                time.sleep(delay)
                continue
            break

    raise RuntimeError(f"NVIDIA failed after retries: {last_error}")


# ============================================================
# MARKDOWN TRANSLATION
# ============================================================

# Regex patterns for protecting non-translatable regions.
# Order matters: longer/more specific patterns first.

# Phase 1: Block-level protections (entire regions)
BLOCK_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Fenced code blocks
    (re.compile(r"````[\s\S]*?````", re.DOTALL), "fence4"),
    (re.compile(r"```[\s\S]*?```", re.DOTALL), "fence"),
    (re.compile(r"~~~~[\s\S]*?~~~~", re.DOTALL), "tilde4"),
    (re.compile(r"~~~[\s\S]*?~~~", re.DOTALL), "tilde"),
    # VitePress containers (whole block)
    (re.compile(r"^:::\s*(?:tip|info|warning|danger|details)\b.*?^:::", re.DOTALL | re.MULTILINE), "container"),
    # HTML blocks
    (re.compile(r"<script[\s\S]*?</script>", re.I), "html"),
    (re.compile(r"<style[\s\S]*?</style>", re.I), "html"),
    (re.compile(r"<!--[\s\S]*?-->", re.I), "html"),
    # Vue/VitePress components: <ComponentName ... /> or <ComponentName ...>...</ComponentName>
    (re.compile(r"<[A-Z][a-zA-Z0-9]*(?:\s[^>]*)?\s*/>"), "vue"),
    (re.compile(r"<[A-Z][a-zA-Z0-9]*(?:\s[^>]*)?>[\s\S]*?</[A-Z][a-zA-Z0-9]*>"), "vue"),
    # HTML tags with content (block-level)
    (re.compile(r"<(?:div|p|span|section|article|header|footer|nav|main|aside|figure|figcaption|blockquote|li|td|th|h[1-6])\b[^>]*>[\s\S]*?</(?:div|p|span|section|article|header|footer|nav|main|aside|figure|figcaption|blockquote|li|td|th|h[1-6])>", re.I), "html"),
    # Self-closing HTML tags
    (re.compile(r"<(?:img|br|hr|input|source|link|meta)\b[^>]*/?>", re.I), "html"),
]

# Phase 2: Inline protections (within lines, after blocks are removed)
INLINE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Inline code
    (re.compile(r"`[^`\n]+`"), "code"),
    # Images: ![alt](url) — protect entire syntax (alt text usually decorative)
    (re.compile(r"!\[[^\]]*\]\([^)]+\)"), "image"),
    # VitePress reference links: [text][ref] — protect entire syntax
    (re.compile(r"\[[^\]]+\]\[[^\]]*\]"), "reflink"),
    # Markdown URLs: <url>
    (re.compile(r"<(https?://[^>]+)>"), "autolink"),
]


def extract_frontmatter_translatables(frontmatter: str) -> List[dict]:
    """
    Extract translatable string values from YAML frontmatter.

    Translates string values (title, description, details, etc.)
    but preserves keys, dates, arrays of tags, and code expressions.

    FIX: Improved YAML parsing to handle quoted strings with escapes better.
    """
    segments = []
    lines = frontmatter.split('\n')

    for i, line in enumerate(lines):
        # Match YAML key: value patterns with quoted or unquoted strings
        # Handles both simple and array formats:
        #   title: "My Title"
        #   - title: "My Title"
        #   details: "Some description"
        
        # Try double-quoted strings first (handle escapes)
        match = re.match(r'^(\s*-?\s*[a-zA-Z_-]+:\s+)"((?:\\.|[^"\\])*)"', line)
        if not match:
            # Try single-quoted strings
            match = re.match(r"^(\s*-?\s*[a-zA-Z_-]+:\s+)'((?:\\'|[^'\\])*)'", line)
            quote_char = "'"
        else:
            quote_char = '"'
        
        if not match:
            # Try unquoted values (but be conservative - only alphanumeric + basic punctuation)
            match = re.match(r'^(\s*-?\s*[a-zA-Z_-]+:\s+)([^\n#]+?)(?:\s*#.*)?$', line)
            if match:
                key_part = match.group(1)
                value_part = match.group(2).strip()
                quote_char = None
            else:
                # Couldn't parse this line - preserve it
                segments.append({"text": line, "type": "frontmatter_line", "line_idx": i, "protected": True})
                continue
        else:
            key_part = match.group(1)
            value_part = match.group(2)
            # Unescape the string if quoted
            if quote_char == '"':
                value_part = value_part.replace('\\"', '"')
            elif quote_char == "'":
                value_part = value_part.replace("\\'", "'")

        # Extract key name (strip leading "- " if present)
        key_name = re.sub(r'^\s*-?\s*', '', key_part).strip().rstrip(':').lower()
        translatable_keys = {
            'title', 'description', 'details', 'name', 'tagline',
            'label', 'text', 'placeholder', 'hero'
        }
        
        if key_name in translatable_keys and len(value_part.strip()) >= MIN_TEXT_LENGTH:
            segments.append({
                "text": value_part,
                "type": "frontmatter_value",
                "line_idx": i,
                "key": key_name,
                "quote": quote_char or '"',
                "full_key": key_part.rstrip() + " ",  # ensure space after colon
            })
        else:
            # Protected line - preserve original text
            segments.append({"text": line, "type": "frontmatter_line", "line_idx": i, "protected": True})

    return segments


def extract_translatables(md: str) -> List[dict]:
    """
    Extract translatable text units from Markdown.

    Strategy:
    1. Handle frontmatter separately (translate string values)
    2. Block-level protections (code blocks, HTML blocks)
    3. Inline protections (inline code, images, URLs)
    4. Handle links specially: protect URL but leave text translatable
    5. Extract remaining prose segments

    FIX: Links are now properly added to protected list and handled in reassembly.
    """
    segments = []

    # Phase 0: Handle frontmatter
    fm_match = re.match(r"^(---\n.*?\n---\n?)", md, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        fm_segments = extract_frontmatter_translatables(fm_text)
        segments.extend(fm_segments)
        md = md[fm_match.end():]

    working = md
    protected = []

    # Phase 1: Block-level protections
    for pattern, kind in BLOCK_PATTERNS:
        for match in pattern.finditer(working):
            start, end = match.start(), match.end()
            overlaps = any(start < p_end and end > p_start for p_start, p_end, _, _ in protected)
            if not overlaps:
                protected.append((start, end, match.group(0), kind))

    # Phase 2: Inline protections (on remaining text)
    # First, collect unprotected regions
    unprotected_regions = []
    protected.sort(key=lambda x: x[0])
    pos = 0
    for start, end, _, _ in protected:
        if start > pos:
            unprotected_regions.append((pos, start))
        pos = end
    if pos < len(working):
        unprotected_regions.append((pos, len(working)))

    # Find inline patterns within unprotected regions
    inline_protected = []
    for region_start, region_end in unprotected_regions:
        region_text = working[region_start:region_end]
        for pattern, kind in INLINE_PATTERNS:
            for match in pattern.finditer(region_text):
                abs_start = region_start + match.start()
                abs_end = region_start + match.end()
                overlaps = any(abs_start < p_end and abs_end > p_start for p_start, p_end, _, _ in protected)
                overlaps = overlaps or any(abs_start < p_end and abs_end > p_start for p_start, p_end, _, _ in inline_protected)
                if not overlaps:
                    inline_protected.append((abs_start, abs_end, match.group(0), kind))

    protected.extend(inline_protected)
    protected.sort(key=lambda x: x[0])

    # Phase 3: Handle links — extract text for translation, protect URL
    # Find all links in unprotected regions and add to protected list
    link_data = {}  # Map (start, end) -> (link_text, link_url)
    
    for region_start, region_end in unprotected_regions:
        region_text = working[region_start:region_end]
        for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", region_text):
            full_start = region_start + match.start()
            full_end = region_start + match.end()
            # Check if this link overlaps with existing protections
            overlaps = any(full_start < p_end and full_end > p_start for p_start, p_end, _, _ in protected)
            if not overlaps:
                link_text = match.group(1)
                link_url = match.group(2)
                # Store link data and mark as protected
                link_data[(full_start, full_end)] = (link_text, link_url)
                protected.append((full_start, full_end, match.group(0), "link"))

    protected.sort(key=lambda x: x[0])

    # Phase 4: Build segments from protected and unprotected regions
    pos = 0
    for start, end, content, kind in protected:
        if start > pos:
            text = working[pos:start]
            segments.append({"text": text, "type": "prose"})
        
        # Special handling for links: split into components
        if kind == "link" and (start, end) in link_data:
            link_text, link_url = link_data[(start, end)]
            if len(link_text.strip()) >= MIN_TEXT_LENGTH:
                # Link text is long enough to translate - split into parts
                segments.append({"text": "[", "type": "protected:link_bracket", "protected": True})
                segments.append({"text": link_text, "type": "link_text"})
                segments.append({"text": "](", "type": "protected:link_bracket", "protected": True})
                segments.append({"text": link_url, "type": "protected:link_url", "protected": True})
                segments.append({"text": ")", "type": "protected:link_bracket", "protected": True})
            else:
                # Short link text - protect entire thing
                segments.append({"text": content, "type": f"protected:{kind}", "protected": True})
        else:
            # Regular protected content
            segments.append({"text": content, "type": f"protected:{kind}", "protected": True})
        
        pos = end

    if pos < len(working):
        text = working[pos:]
        segments.append({"text": text, "type": "prose"})

    return segments


def translate_markdown(
    md: str,
    target_lang: str,
    api_key: str,
    cache: dict,
    stats: dict,
    lock: threading.Lock,
) -> str:
    """
    Translate a Markdown document.

    1. Extract translatable text units
    2. Deduplicate globally
    3. Look up cache, send misses to NVIDIA
    4. Reassemble document

    FIX: Improved frontmatter newline handling - preserves original line structure.
    """
    segments = extract_translatables(md)

    # Collect unique translatable strings
    unique_texts = {}
    for seg in segments:
        if seg.get("protected"):
            continue
        text = seg["text"]
        norm = re.sub(r"\s+", " ", text.strip())
        if len(norm) < MIN_TEXT_LENGTH or len(norm) > MAX_TEXT_LENGTH:
            continue
        if norm not in unique_texts:
            unique_texts[norm] = text

    # Check cache for all unique texts
    to_translate = {}
    for norm, original in unique_texts.items():
        cached = cache_get(cache, original, target_lang)
        if cached is not None:
            with lock:
                stats["cache_hits"] += 1
        else:
            to_translate[norm] = original
            with lock:
                stats["cache_misses"] += 1

    # Translate missing texts (one NVIDIA request per unique string)
    translations = {}
    for norm, original in to_translate.items():
        try:
            translated = nim_translate(original, target_lang, api_key)
            with lock:
                cache_put(cache, original, target_lang, translated)
                stats["nvidia_requests"] += 1
            translations[norm] = translated
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            print(f"      ERROR translating {norm[:60]!r}: {e}")
            translations[norm] = original  # fallback to English

    # Reassemble: replace translatable segments with translations
    result = []
    for seg in segments:
        text = seg["text"]
        seg_type = seg.get("type", "")

        # Handle frontmatter lines (protected) - preserve original line structure
        if seg_type == "frontmatter_line":
            # Check if line already ends with newline in source
            if text.endswith('\n'):
                result.append(text)
            else:
                # Only add newline if not already present
                # (Original frontmatter lines in split('\n') won't have trailing \n except the last)
                result.append(text + "\n")
            continue

        # Handle frontmatter value segments
        if seg_type == "frontmatter_value":
            norm = re.sub(r"\s+", " ", text.strip())
            if norm in translations:
                translated = translations[norm]
            else:
                translated = text
            # Rebuild the YAML line using full_key prefix
            full_key = seg.get("full_key", f'{seg.get("key", "title")}: ')
            quote = seg.get("quote", '"')
            # Escape quotes in translated text if needed
            if quote == '"':
                translated_escaped = translated.replace('"', '\\"')
            elif quote == "'":
                translated_escaped = translated.replace("'", "\\'")
            else:
                translated_escaped = translated
            result.append(f'{full_key}{quote}{translated_escaped}{quote}\n')
            continue

        # Handle link text segments (translatable)
        if seg_type == "link_text":
            norm = re.sub(r"\s+", " ", text.strip())
            if norm in translations:
                result.append(translations[norm])
            else:
                result.append(text)
            continue

        # Handle protected segments
        if seg.get("protected"):
            result.append(text)
            continue

        # Handle prose segments
        norm = re.sub(r"\s+", " ", text.strip())
        if norm in translations:
            # Preserve leading/trailing whitespace
            lead = re.match(r"^\s*", text).group(0)
            trail = re.search(r"\s*$", text).group(0)
            result.append(lead + translations[norm] + trail)
        else:
            result.append(text)

    return "".join(result)


# ============================================================
# FILE DISCOVERY
# ============================================================

def fix_relative_paths(md: str, source_rel: Path, target_lang: str) -> str:
    """
    Fix relative paths in translated markdown.

    When translating docs/tags/index.md → docs/vi/tags/index.md,
    paths like ../.vitepress need to become ../../.vitepress.
    """
    depth = len(source_rel.parts) - 1  # -1 for the filename itself
    
    # Build prefix for relative path adjustment
    # If we're at docs/vi/tags/index.md and reference ../.. we need to add one more ../
    if depth > 0:
        extra_prefix = "../"
    else:
        extra_prefix = ""

    def fix_relative_path(match):
        full_text = match.group(0)
        path = match.group(1)
        
        # Only fix relative paths that start with ../
        if path.startswith("../"):
            # Insert extra prefix
            fixed_path = extra_prefix + path
            return full_text.replace(path, fixed_path)
        return full_text

    # Fix relative paths in various contexts
    # from imports
    md = re.sub(r"""from\s+['"](\.\.[^'"]+)['"]""", fix_relative_path, md)
    # import statements
    md = re.sub(r"""import\s+[^;]+from\s+['"](\.\.[^'"]+)['"]""", fix_relative_path, md)
    # Image and link paths should already be protected, but try anyway
    # md = re.sub(r"""!\[[^\]]*\]\((\.\.[^)]+)\)""", fix_relative_path, md)
    # md = re.sub(r"""\[[^\]]+\]\((\.\.[^)]+)\)""", fix_relative_path, md)

    return md


def find_source_pages(docs: Path, lang_dirs: set) -> List[Path]:
    """Find all .md files under docs/, excluding language directories and dynamic routes."""
    pages = []
    for md in docs.rglob("*.md"):
        rel = md.relative_to(docs)
        # Skip language directories
        if rel.parts and rel.parts[0] in lang_dirs:
            continue
        # Skip .vitepress directory
        if ".vitepress" in rel.parts:
            continue
        # Skip dynamic route files like [tag].md
        if "[" in md.name:
            continue
        pages.append(md)
    return sorted(pages)


# ============================================================
# WORKER THREAD
# ============================================================

class TranslationWorker:
    """Thread-safe translation worker."""

    def __init__(self, api_key: str, cache: dict, stats: dict, lock: threading.Lock):
        self.api_key = api_key
        self.cache = cache
        self.stats = stats
        self.lock = lock

    def translate_file(self, md_path: Path, docs: Path, target_lang: str) -> dict:
        """Translate one file for one language. Returns metadata."""
        rel = md_path.relative_to(docs)
        source_hash = file_hash(md_path)

        md = md_path.read_text(encoding="utf-8")

        translated = translate_markdown(
            md, target_lang, self.api_key, self.cache, self.stats, self.lock
        )

        # Fix relative paths for language subdirectory
        translated = fix_relative_paths(translated, rel, target_lang)

        # Write translated file
        out_dir = docs / target_lang / rel.parent
        out_path = out_dir / md_path.name
        atomic_write(out_path, translated)

        return {"rel": str(rel), "hash": source_hash}


# ============================================================
# CLI
# ============================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="VitePress Markdown Translator (NVIDIA NIM)"
    )
    p.add_argument(
        "--langs",
        default=",".join(LANGUAGES.keys()),
        help="Comma-separated target languages (default: all)",
    )
    p.add_argument(
        "--docs",
        type=Path,
        default=DOCS_DIR,
        help="Source docs directory (default: docs/)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel translation workers (default: 4)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be translated without calling NVIDIA",
    )
    p.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete translation cache before starting",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Force retranslation (still uses string cache)",
    )
    return p.parse_args()


# ============================================================
# MAIN
# ============================================================

def main():
    args = parse_args()

    # API key check
    if not args.dry_run and not API_KEY:
        print("ERROR: NVIDIA_API_KEY is not set.")
        print()
        print('Run: export NVIDIA_API_KEY="nvapi-..."')
        print()
        print("For Cloudflare Pages:")
        print("  1. Go to Pages → your project → Settings → Build")
        print("  2. Add build variable: NVIDIA_API_KEY = nvapi-...")
        print("  3. Branch: All (not a specific branch)")
        sys.exit(1)

    # Validate API key with a test request
    if not args.dry_run and API_KEY:
        print("Validating NVIDIA API key...")
        try:
            test_resp = requests.post(
                NIM_ENDPOINT,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": NIM_MODEL,
                    "messages": [{"role": "system", "content": "en-vi"}, {"role": "user", "content": "Hello"}],
                    "temperature": 0,
                    "max_tokens": 100,
                },
                timeout=30,
            )
            if test_resp.status_code == 403:
                print(f"ERROR: NVIDIA API key is invalid or expired.")
                print(f"Response: {test_resp.text[:300]}")
                print()
                print("Please check your NVIDIA_API_KEY in Cloudflare Pages build variables.")
                sys.exit(1)
            elif not test_resp.ok:
                print(f"WARNING: NVIDIA API returned HTTP {test_resp.status_code}")
                print(f"Response: {test_resp.text[:300]}")
            else:
                print("API key validated successfully.")
        except Exception as e:
            print(f"WARNING: Could not validate API key: {e}")
            print("Continuing anyway...")

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

    # Language dirs to exclude from source scan
    lang_dirs = set(LANGUAGES.keys())

    # Parse languages
    requested = [c.strip() for c in args.langs.split(",") if c.strip()]
    for lang in requested:
        if lang not in LANGUAGES:
            print(f"ERROR: unknown language '{lang}'")
            print(f"Supported: {', '.join(LANGUAGES.keys())}")
            sys.exit(1)

    # Find source pages
    pages = find_source_pages(docs, lang_dirs)

    # Load state and cache
    state = load_state()
    cache = load_cache()

    # Header
    print()
    print("VitePress Markdown Translator")
    print("=" * 50)
    print(f"Source:    {docs}")
    print(f"Pages:     {len(pages)}")
    print(f"Languages: {', '.join(requested)}")
    print(f"Workers:   {args.workers}")
    print(f"Model:     {NIM_MODEL}")
    print()

    if args.dry_run:
        print("DRY RUN: no NVIDIA requests will be made.")
        print()

    # Global stats
    stats = {
        "cache_hits": 0,
        "cache_misses": 0,
        "nvidia_requests": 0,
    }

    lock = threading.Lock()

    total_scanned = 0
    total_translated = 0
    total_skipped = 0

    for lang in requested:
        lang_name = LANGUAGES[lang]
        print(f"[{lang}] {lang_name}")

        pages_skipped = 0
        pages_translated = 0

        # Filter pages that need translation
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
            worker = TranslationWorker(API_KEY, cache, stats, lock)

            def do_task(task):
                md_path, h = task
                result = worker.translate_file(md_path, docs, lang)
                with lock:
                    page_mark_done(state, result["rel"], result["hash"], lang)
                rel = md_path.relative_to(docs)
                print(f"  {str(rel):50s} DONE")
                return result

            if args.workers <= 1:
                for task in tasks:
                    try:
                        do_task(task)
                    except Exception as e:
                        print(f"  ERROR: {e}")
                        sys.exit(1)
            else:
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = {pool.submit(do_task, t): t for t in tasks}
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            print(f"  ERROR: {e}")
                            sys.exit(1)

            # Save cache and state after each language
            save_cache(cache)
            save_state(state)

        print()

    # Final stats
    print("=" * 50)
    print("Translation complete.")
    print()
    print(f"Pages scanned:    {len(pages) * len(requested)}")
    print(f"Cache hits:       {stats['cache_hits']}")
    print(f"Cache misses:     {stats['cache_misses']}")
    print(f"NVIDIA requests:  {stats['nvidia_requests']}")
    print()
    print(f"Cache:  {CACHE_FILE}")
    print(f"State:  {STATE_FILE}")
    print(f"Output: {docs}/{{lang}}/")
    print()


if __name__ == "__main__":
    main()