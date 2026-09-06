#!/usr/bin/env python3
"""Lightweight tests for the VitePress Markdown Translator."""

import re
import sys
import os

# Ensure translate.py can be imported
sys.path.insert(0, os.path.dirname(__file__))

from translate import (
    Protector, prose_only, extract_frontmatter, split_into_chunks,
    merge_small_chunks, post_process, cache_key, page_needs_translation,
    TRANSLATABLE_FRONTMATTER_KEYS, MIN_TEXT_LENGTH, MIN_CHUNK_PROSE,
)

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f"  --  {detail}"
        print(msg)


# ============================================================
# PROTECTOR TESTS
# ============================================================

print("\n=== Protector ===")

p = Protector()

# Basic roundtrip
md = "# Hello World\n\nThis is a test."
protected = p.protect(md)
restored = p.restore(protected)
check("basic roundtrip", restored == md)

# Fenced code block
p = Protector()
md = "Before\n\n```python\nprint('hello')\n```\n\nAfter"
protected = p.protect(md)
check("code fence protected", "```python" not in protected.split("\n\n")[1])
restored = p.restore(protected)
check("code fence restored", restored == md)

# Inline code
p = Protector()
md = "Use `npm install` to install."
protected = p.protect(md)
check("inline code protected", "`npm install`" not in protected)
restored = p.restore(protected)
check("inline code restored", restored == md)

# Image
p = Protector()
md = "![alt text](https://example.com/img.png)"
protected = p.protect(md)
check("image protected", "![" not in protected)
restored = p.restore(protected)
check("image restored", restored == md)

# Link with URL protection
p = Protector()
md = "Check [this link](https://example.com) for details."
protected = p.protect(md)
check("link URL protected", "https://example.com" not in protected)
check("link text preserved", "this link" in protected)
restored = p.restore(protected)
check("link restored", restored == md)

# Link with inline code (overlap bug fix)
p = Protector()
md = "Install [`npm`](https://npmjs.com) globally."
protected = p.protect(md)
check("code-in-link URL protected", "https://npmjs.com" not in protected)
restored = p.restore(protected)
check("code-in-link restored", restored == md)

# VitePress container
p = Protector()
md = "::: tip\nUse `npm install` first.\n:::"
protected = p.protect(md)
check("container protected", "::: tip" not in protected)
restored = p.restore(protected)
check("container restored", restored == md)

# Vue component
p = Protector()
md = "<MyComponent prop=\"value\" />"
protected = p.protect(md)
check("vue component protected", "<MyComponent" not in protected)
restored = p.restore(protected)
check("vue component restored", restored == md)

# HTML tag
p = Protector()
md = "<div class=\"test\">Content</div>"
protected = p.protect(md)
check("html div protected", "<div" not in protected)
restored = p.restore(protected)
check("html div restored", restored == md)

# VitePress template expression
p = Protector()
md = "Title: {{ $frontmatter.title }}"
protected = p.protect(md)
check("template expr protected", "{{ $frontmatter.title }}" not in protected)
restored = p.restore(protected)
check("template expr restored", restored == md)

# Autolink
p = Protector()
md = "Visit <https://example.com> now."
protected = p.protect(md)
check("autolink protected", "<https://example.com>" not in protected)
restored = p.restore(protected)
check("autolink restored", restored == md)

# Validation
p = Protector()
md = "# Test\n\nUse `npm install` to start."
protected = p.protect(md)
check("validation catches unrestored", len(re.findall(r"__PH_\d+__", protected)) > 0)
# Simulate broken restoration (placeholder left unrestored)
broken = protected  # leave placeholders as-is (not restored)
errors = p.validate_restored(md, broken)
check("validation catches unrestored", len(errors) > 0)

p = Protector()
md = "# Test\n\nUse `npm install` to start."
protected = p.protect(md)
restored = p.restore(protected)
errors = p.validate_restored(md, restored)
check("validation passes clean", len(errors) == 0)


# ============================================================
# PROSE_ONLY TESTS
# ============================================================

print("\n=== prose_only ===")

check("strips placeholders", prose_only("Hello __PH_0__ world") == "Hello  world")
check("strips headings", prose_only("## Hello") == "Hello")
check("strips bold", prose_only("**bold** text") == "bold text")
check("strips inline code", prose_only("`code` text") == "code text")


# ============================================================
# FRONTMATTER TESTS
# ============================================================

print("\n=== extract_frontmatter ===")

fm, body = extract_frontmatter("---\ntitle: Hello\n---\n\nBody here.")
check("extracts frontmatter", fm is not None and "title: Hello" in fm)
check("extracts body", "Body here." in body)

fm, body = extract_frontmatter("No frontmatter here.")
check("no frontmatter returns None", fm is None)
check("no frontmatter returns full body", body == "No frontmatter here.")


# ============================================================
# SPLITTING TESTS
# ============================================================

print("\n=== split_into_chunks ===")

# Small text stays as one chunk
chunks = split_into_chunks("Small text.")
check("small text one chunk", len(chunks) == 1)

# Large text splits
big = "\n\n".join(["Paragraph " + str(i) + " " + "x" * 200 for i in range(50)])
chunks = split_into_chunks(big)
check("large text splits", len(chunks) > 1)
check("no chunk exceeds limit", all(len(c) <= 9000 for c in chunks))

# Merged chunks have prose
for c in chunks:
    p = prose_only(c)
    check(f"chunk has prose ({len(p)} chars)", len(p) >= MIN_TEXT_LENGTH)


# ============================================================
# MERGE_SMALL_CHUNKS TESTS
# ============================================================

print("\n=== merge_small_chunks ===")

# Single chunk unchanged
check("single chunk unchanged", merge_small_chunks(["hello"]) == ["hello"])

# Small chunks get merged
small = ["a" * 100, "b" * 100, "c" * 1000, "d" * 100]
merged = merge_small_chunks(small, min_size=500)
check("small chunks merged", len(merged) < len(small))

# Large chunks stay separate
big = ["a" * 1000, "b" * 1000, "c" * 1000]
merged = merge_small_chunks(big, min_size=500)
check("big chunks stay separate", len(merged) == 3)


# ============================================================
# POST_PROCESS TESTS
# ============================================================

print("\n=== post_process ===")

check("vi spacing fix", post_process("Hello !", "vi") == "Hello!")
check("link spacing fix", post_process("text ] (url)", "vi") ==("text ](url)"))
check("double space fix", post_process("a  b  c", "vi") == "a b c")


# ============================================================
# CACHE KEY TESTS
# ============================================================

print("\n=== cache_key ===")

k1 = cache_key("Hello world", "vi")
k2 = cache_key("Hello world", "vi")
check("same input same key", k1 == k2)

k3 = cache_key("Hello world", "fr")
check("different lang different key", k1 != k3)

k4 = cache_key("Hello World", "vi")
check("different case different key", k1 != k4)


# ============================================================
# PAGE STATE TESTS
# ============================================================

print("\n=== page_needs_translation ===")

state = {"pages": {}}
check("new page needs translation", page_needs_translation(state, "test.md", "abc", "vi", False))

state["pages"]["vi:test.md"] = {"hash": "abc"}
check("unchanged page skips", not page_needs_translation(state, "test.md", "abc", "vi", False))

check("changed page translates", page_needs_translation(state, "test.md", "xyz", "vi", False))

check("force always translates", page_needs_translation(state, "test.md", "abc", "vi", True))


# ============================================================
# INTEGRATION: contact.md simulation
# ============================================================

print("\n=== contact.md simulation ===")

contact_md = """---
layout: home
title: Contact me!
hero:
    name: Contact me!
    title: ...from different methods.
---

# Contacting is easy, but make sure it follow these details:

::: details Am I/are we allowed to send you invoices about our products and sponsorships?
- Bah! I do not like that corporate energy! Besides that, nah...
:::

::: details Am I/are we allowed to send NSFW to you?
- No, but if you somehow sent me these, I'm going to bleach my eyes...
:::

# Ready to contact?

::: details Email addresses
[italia.troller@italiatroller.qzz.io](mailto:italia.troller@italiatroller.qzz.io)
:::
"""

p = Protector()
fm, body = extract_frontmatter(contact_md)
protected = p.protect(body)

# Count placeholders
ph_count = len(re.findall(r"__PH_\d+__", protected))
check(f"contact.md has {ph_count} placeholders", ph_count > 0)

# Check that prose is still there
prose = prose_only(protected)
check("contact.md prose preserved", "Contacting is easy" in prose)
check("contact.md email protected", "italia.troller@" not in protected)

# Restore
restored = p.restore(protected)
check("contact.md roundtrip", restored == body)

# Frontmatter not translated (keys not in translatable set)
check("layout not translatable", "layout" not in TRANSLATABLE_FRONTMATTER_KEYS)
check("title is translatable", "title" in TRANSLATABLE_FRONTMATTER_KEYS)


# ============================================================
# RESULTS
# ============================================================

print()
print("=" * 50)
print(f"Results: {PASS} passed, {FAIL} failed")
print("=" * 50)

sys.exit(1 if FAIL > 0 else 0)
