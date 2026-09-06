package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestProtectAndRestore(t *testing.T) {
	text := "Hello `code` and ![img](x.png) and [link](https://example.com) and ```js\nconst x = 1\n``` and {{foo}}."
	protected, items := protect(text)
	if !strings.Contains(protected, "__PH_") {
		t.Fatalf("expected protected text to include placeholders, got %q", protected)
	}
	if len(items) == 0 {
		t.Fatal("expected placeholder items to be created")
	}
	restored := restore(protected, items)
	if restored != text {
		t.Fatalf("restore mismatch\nwant: %q\n got: %q", text, restored)
	}
}

func TestExtractFrontmatter(t *testing.T) {
	md := "---\ntitle: \"Hello\"\ndescription: World\n---\n\n# Page\n"
	fm, body := extractFrontmatter(md)
	if fm == "" || body == "" {
		t.Fatal("expected frontmatter and body")
	}
	if !strings.Contains(fm, "title:") || !strings.Contains(body, "# Page") {
		t.Fatalf("unexpected split: fm=%q body=%q", fm, body)
	}
}

func TestFixRelativePaths(t *testing.T) {
	md := "import x from '../shared.js'\nconst y = require(\"../foo\")\n"
	fixed := fixRelativePaths(md, filepath.Join("guides", "posts", "article.md"))
	if !strings.Contains(fixed, "../../shared.js") || !strings.Contains(fixed, "../../foo") {
		t.Fatalf("unexpected relative fix: %q", fixed)
	}
}

func TestFindSourcePages(t *testing.T) {
	tmp := t.TempDir()
	_ = os.MkdirAll(filepath.Join(tmp, "docs", "g1"), 0o755)
	_ = os.WriteFile(filepath.Join(tmp, "docs", "a.md"), []byte("hi"), 0o644)
	_ = os.WriteFile(filepath.Join(tmp, "docs", "g1", "b.md"), []byte("hi"), 0o644)
	_ = os.WriteFile(filepath.Join(tmp, "docs", "fr", "c.md"), []byte("hi"), 0o644)
	pages := findSourcePages(filepath.Join(tmp, "docs"), map[string]string{"fr": "French"})
	if len(pages) != 2 {
		t.Fatalf("expected 2 source pages, got %d: %#v", len(pages), pages)
	}
}
