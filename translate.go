package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	cacheVersion          = 8
	minTextLength         = 2
	defaultTimeoutSeconds = 120
	defaultMaxRetries     = 2
	defaultModel          = "poolside/laguna-xs-2.1"
	defaultBaseURL        = "https://integrate.api.nvidia.com/v1"
)

var languages = map[string]string{"vi": "Vietnamese", "fr": "French", "ja": "Japanese"}
var translatableFMKeys = map[string]struct{}{
	"title": {}, "description": {}, "details": {}, "name": {}, "tagline": {},
	"label": {}, "text": {}, "placeholder": {}, "hero": {},
}

var placeholderPattern = regexp.MustCompile(`__PH_\d+__`)

type options struct {
	Langs          string
	Docs           string
	Workers        int
	DryRun         bool
	ClearCache     bool
	Force          bool
	Strict         bool
	SkipValidation bool
	Help           bool
}

type cacheData struct {
	V int                   `json:"v"`
	E map[string]cacheEntry `json:"e"`
}

type cacheEntry struct {
	R  string `json:"r"`
	TS int64  `json:"ts"`
}

type stateData struct {
	V int                   `json:"v"`
	P map[string]pageStatus `json:"p"`
}

type pageStatus struct {
	H  string `json:"h"`
	TS int64  `json:"ts"`
}

type pageTask struct {
	MDPath string
	Rel    string
	Hash   string
}

type stats struct {
	CacheHits   int
	CacheMisses int
	APIRequests int
}

func main() {
	cfg := parseArgs()
	if cfg.Help {
		fmt.Printf(`VitePress Markdown Translator

Usage: go run translate.go [options]

Options:
  --langs <list>      Languages (default: %s)
  --docs <path>       Source docs dir (default: docs/)
  --workers <n>       Workers (default: %d)
  --dry-run           Dry run
  --clear-cache       Clear cache
  --force             Force retranslate
  --strict            Fail on errors
  --skip-validation   Skip API validation
`, strings.Join(sortedKeys(languages), ","), cfg.Workers)
		return
	}

	if !cfg.DryRun && strings.TrimSpace(os.Getenv("TRANSLATION_API_KEY"))+strings.TrimSpace(os.Getenv("NVIDIA_API_KEY")) == "" {
		fmt.Println("ERROR: NVIDIA_API_KEY (or TRANSLATION_API_KEY) is not set.")
		fmt.Println("Run: export NVIDIA_API_KEY=\"nvapi-...\"")
		fmt.Println("For Cloudflare Pages:")
		fmt.Println("  1. Pages -> your project -> Settings -> Build")
		fmt.Println("  2. Add build variable: NVIDIA_API_KEY = nvapi-...")
		os.Exit(1)
	}

	if !cfg.DryRun && !cfg.SkipValidation {
		if err := validateAPIKey(); err != nil {
			fmt.Printf("WARNING: Could not validate API key: %v\n", err)
		}
	}

	if cfg.ClearCache {
		for _, p := range []string{
			filepath.Join(cfg.Docs, ".vitepress", "translation-cache.json"),
			filepath.Join(cfg.Docs, ".vitepress", "translation-state.json"),
		} {
			if err := os.Remove(p); err == nil {
				fmt.Printf("Deleted: %s\n", p)
			}
		}
	}

	docsDir, err := filepath.Abs(cfg.Docs)
	if err != nil {
		fatal(err)
	}
	info, err := os.Stat(docsDir)
	if err != nil || !info.IsDir() {
		fmt.Printf("ERROR: docs directory not found: %s\n", docsDir)
		os.Exit(1)
	}

	requested := splitCSV(cfg.Langs)
	for _, lang := range requested {
		if _, ok := languages[lang]; !ok {
			fmt.Printf("ERROR: unknown language '%s'\n", lang)
			fmt.Printf("Supported: %s\n", strings.Join(sortedKeys(languages), ", "))
			os.Exit(1)
		}
	}

	pages := findSourcePages(docsDir, languages)
	state := loadState(filepath.Join(docsDir, ".vitepress", "translation-state.json"))
	cache := loadCache(filepath.Join(docsDir, ".vitepress", "translation-cache.json"))

	fmt.Println()
	fmt.Println("VitePress Markdown Translator")
	fmt.Println(strings.Repeat("=", 50))
	fmt.Printf("Source:    %s\n", docsDir)
	fmt.Printf("Pages:     %d\n", len(pages))
	fmt.Printf("Languages: %s\n", strings.Join(requested, ", "))
	fmt.Printf("Workers:   %d\n", cfg.Workers)
	fmt.Printf("Model:     %s\n", modelName())
	fmt.Println()

	if cfg.DryRun {
		fmt.Println("DRY RUN: no API calls will be made.")
	}

	if !cfg.DryRun {
		issues := []string{}
		for _, mdPath := range pages {
			if res := preValidatePage(mdPath); len(res) > 0 {
				issues = append(issues, fmt.Sprintf("%s: %s", filepath.ToSlash(relPath(docsDir, mdPath)), strings.Join(res, "; ")))
			}
		}
		if len(issues) > 0 {
			fmt.Println("VALIDATION ERRORS:")
			for _, item := range issues {
				fmt.Println("  " + item)
			}
			if cfg.Strict {
				os.Exit(1)
			}
		}
	}

	stats := &stats{}
	start := time.Now()

	for _, lang := range requested {
		fmt.Printf("[%s] %s\n", lang, languages[lang])
		pagesSkipped := 0
		pagesTranslated := 0
		var tasks []pageTask

		for _, mdPath := range pages {
			rel := relPath(docsDir, mdPath)
			h, err := fileHash(mdPath)
			if err != nil {
				fatal(err)
			}
			if !pageNeedsTranslation(state, rel, h, lang, cfg.Force) {
				pagesSkipped++
				if !cfg.DryRun {
					fmt.Printf("  %-50s SKIP\n", rel)
				}
				continue
			}
			pagesTranslated++
			if cfg.DryRun {
				fmt.Printf("  %-50s WOULD TRANSLATE\n", rel)
			} else {
				tasks = append(tasks, pageTask{MDPath: mdPath, Rel: rel, Hash: h})
			}
		}

		fmt.Printf("  pages skipped: %d\n", pagesSkipped)
		fmt.Printf("  pages changed: %d\n", pagesTranslated)

		if !cfg.DryRun && len(tasks) > 0 {
			for _, task := range tasks {
				t0 := time.Now()
				translated, err := translateOnePage(task.MDPath, lang, cache, stats, cfg.Strict)
				if err != nil {
					fmt.Printf("      ERROR: %v\n", err)
					if cfg.Strict {
						os.Exit(1)
					}
					continue
				}
				fixed := fixRelativePaths(translated, task.Rel)
				outPath := filepath.Join(docsDir, lang, task.Rel)
				if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
					fatal(err)
				}
				if err := os.WriteFile(outPath, []byte(fixed), 0o644); err != nil {
					fatal(err)
				}
				pageMarkDone(state, task.Rel, task.Hash, lang)
				fmt.Printf("  %-50s DONE (%ss)\n", task.Rel, strconv.FormatFloat(time.Since(t0).Seconds(), 'f', 1, 64))
			}
			saveCache(filepath.Join(docsDir, ".vitepress", "translation-cache.json"), cache)
			saveState(filepath.Join(docsDir, ".vitepress", "translation-state.json"), state)
		}
		fmt.Println()
	}

	fmt.Println(strings.Repeat("=", 50))
	fmt.Println("Translation complete.")
	fmt.Printf("Total time:      %ss\n", strconv.FormatFloat(time.Since(start).Seconds(), 'f', 1, 64))
	fmt.Printf("Pages scanned:   %d\n", len(pages)*len(requested))
	fmt.Printf("Cache hits:      %d\n", stats.CacheHits)
	fmt.Printf("Cache misses:    %d\n", stats.CacheMisses)
	fmt.Printf("API requests:    %d\n\n", stats.APIRequests)
	fmt.Printf("Cache:  %s\n", filepath.Join(docsDir, ".vitepress", "translation-cache.json"))
	fmt.Printf("State:  %s\n", filepath.Join(docsDir, ".vitepress", "translation-state.json"))
	fmt.Printf("Output: %s/{lang}/\n", docsDir)
	if cfg.Strict {
		fmt.Println("Mode:   STRICT (errors cause exit)")
	}
	fmt.Println()
}

func parseArgs() options {
	var cfg options
	fs := flag.NewFlagSet("translate", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	fs.StringVar(&cfg.Langs, "langs", strings.Join(sortedKeys(languages), ","), "")
	fs.StringVar(&cfg.Docs, "docs", "docs", "")
	fs.IntVar(&cfg.Workers, "workers", 2, "")
	fs.BoolVar(&cfg.DryRun, "dry-run", false, "")
	fs.BoolVar(&cfg.ClearCache, "clear-cache", false, "")
	fs.BoolVar(&cfg.Force, "force", false, "")
	fs.BoolVar(&cfg.Strict, "strict", false, "")
	fs.BoolVar(&cfg.SkipValidation, "skip-validation", false, "")
	fs.BoolVar(&cfg.Help, "help", false, "")
	_ = fs.Parse(os.Args[1:])
	return cfg
}

func sortedKeys(m map[string]string) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func splitCSV(s string) []string {
	parts := strings.Split(s, ",")
	res := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			res = append(res, p)
		}
	}
	return res
}

func relPath(base, path string) string {
	p, err := filepath.Rel(base, path)
	if err != nil {
		return path
	}
	return filepath.ToSlash(p)
}

func fileHash(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func loadCache(path string) map[string]cacheEntry {
	data := cacheData{V: cacheVersion, E: map[string]cacheEntry{}}
	b, err := os.ReadFile(path)
	if err != nil || len(b) == 0 {
		return data.E
	}
	if err := json.Unmarshal(b, &data); err == nil {
		if data.V == cacheVersion && data.E != nil {
			return data.E
		}
	}
	return map[string]cacheEntry{}
}

func saveCache(path string, data map[string]cacheEntry) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		panic(err)
	}
	b, err := json.Marshal(cacheData{V: cacheVersion, E: data})
	if err != nil {
		panic(err)
	}
	if err := os.WriteFile(path, b, 0o644); err != nil {
		panic(err)
	}
}

func loadState(path string) map[string]pageStatus {
	data := stateData{V: cacheVersion, P: map[string]pageStatus{}}
	b, err := os.ReadFile(path)
	if err != nil || len(b) == 0 {
		return data.P
	}
	if err := json.Unmarshal(b, &data); err == nil {
		if data.V == cacheVersion && data.P != nil {
			return data.P
		}
	}
	return map[string]pageStatus{}
}

func saveState(path string, data map[string]pageStatus) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		panic(err)
	}
	b, err := json.Marshal(stateData{V: cacheVersion, P: data})
	if err != nil {
		panic(err)
	}
	if err := os.WriteFile(path, b, 0o644); err != nil {
		panic(err)
	}
}

func pageNeedsTranslation(state map[string]pageStatus, rel, h, lang string, force bool) bool {
	if force {
		return true
	}
	entry, ok := state[lang+":"+rel]
	return !ok || entry.H != h
}

func pageMarkDone(state map[string]pageStatus, rel, h, lang string) {
	state[lang+":"+rel] = pageStatus{H: h, TS: time.Now().Unix()}
}

func protect(text string) (string, map[int]string) {
	patterns := []*regexp.Regexp{
		regexp.MustCompile("(```[\\s\\S]*?```|````[\\s\\S]*?````|~~~[\\s\\S]*?~~~|~~~~[\\s\\S]*?~~~~)"),
		regexp.MustCompile("(?m)^:::\\s*(?:tip|info|warning|danger|details)\\b.*?^:::"),
		regexp.MustCompile("(?is)<script[\\s\\S]*?</script>"),
		regexp.MustCompile("(?is)<style[\\s\\S]*?</style>"),
		regexp.MustCompile("(?is)<!--[\\s\\S]*?-->"),
		regexp.MustCompile("(?is)<(?:img|br|hr|input|source|link|meta)\\b[^>]*>"),
		regexp.MustCompile("(?is)!\\[[^\\]]*\\]\\([^)]+\\)"),
		regexp.MustCompile("(?is)\\[[^\\]]+\\]\\([^)]*\\)"),
		regexp.MustCompile("(?is)<[A-Z][A-Za-z0-9]*(?:\\s[^>]*)?>[\\s\\S]*?</[A-Z][A-Za-z0-9]*>"),
	}

	items := map[int]string{}
	parts := []string{}
	cursor := 0
	for _, re := range patterns {
		for _, match := range re.FindAllStringSubmatchIndex(text, -1) {
			if match[0] < cursor {
				continue
			}
			parts = append(parts, text[cursor:match[0]])
			segment := text[match[0]:match[1]]
			idx := len(items)
			items[idx] = segment
			parts = append(parts, fmt.Sprintf("__PH_%d__", idx))
			cursor = match[1]
		}
	}
	if cursor < len(text) {
		parts = append(parts, text[cursor:])
	}
	return strings.Join(parts, ""), items
}

func restore(text string, items map[int]string) string {
	if len(items) == 0 {
		return text
	}
	keys := make([]int, 0, len(items))
	for k := range items {
		keys = append(keys, k)
	}
	sort.Sort(sort.Reverse(sort.IntSlice(keys)))
	for _, idx := range keys {
		text = strings.ReplaceAll(text, fmt.Sprintf("__PH_%d__", idx), items[idx])
	}
	return text
}

func validatePlaceholders(original, restored string) []string {
	origSet := map[string]int{}
	for _, ph := range placeholderPattern.FindAllString(original, -1) {
		origSet[ph]++
	}
	restSet := map[string]int{}
	for _, ph := range placeholderPattern.FindAllString(restored, -1) {
		restSet[ph]++
	}
	var errs []string
	for ph, count := range origSet {
		if inRest := restSet[ph]; inRest == 0 {
			errs = append(errs, "Missing placeholder: "+ph)
		} else if inRest != count {
			errs = append(errs, fmt.Sprintf("%s appears %dx (expected %d)", ph, inRest, count))
		}
	}
	for ph := range restSet {
		if _, ok := origSet[ph]; !ok {
			errs = append(errs, "Unknown placeholder: "+ph)
		}
	}
	return errs
}

func proseLength(text string) int {
	text = strings.Map(func(r rune) rune {
		if r == '*' || r == '_' || r == '~' || r == '`' {
			return -1
		}
		return r
	}, text)
	text = strings.TrimSpace(text)
	return len(text)
}

func extractFrontmatter(md string) (string, string) {
	if !strings.HasPrefix(md, "---\n") {
		return "", md
	}
	end := strings.Index(md[4:], "\n---\n")
	if end == -1 {
		return "", md
	}
	end += 4
	return md[:end+5], md[end+5:]
}

func translateFrontmatter(fm string, targetLang string, cache map[string]cacheEntry, stats *stats) (string, error) {
	lines := strings.Split(fm, "\n")
	result := make([]string, 0, len(lines))
	for _, line := range lines {
		var keyPart, value, quote string
		m := regexp.MustCompile(`^(\s*-?\s*[a-zA-Z_-]+:\s+")((?:\\.|[^"\\])*)"`).FindStringSubmatch(line)
		if len(m) > 0 {
			keyPart, value, quote = m[1], strings.ReplaceAll(m[2], `\"`, `"`), `"`
		} else {
			m = regexp.MustCompile(`^(\s*-?\s*[a-zA-Z_-]+:\s+')((?:\\'|[^'\\])*)'`).FindStringSubmatch(line)
			if len(m) > 0 {
				keyPart, value, quote = m[1], strings.ReplaceAll(m[2], `\'`, `'`), "'"
			} else {
				m = regexp.MustCompile(`^(\s*-?\s*[a-zA-Z_-]+:\s+)([^\n#]+?)(?:\s*#.*)?$`).FindStringSubmatch(line)
				if len(m) > 0 {
					keyPart, value, quote = m[1], strings.TrimSpace(m[2]), ""
				} else {
					result = append(result, line)
					continue
				}
			}
		}

		keyName := strings.TrimSpace(strings.TrimSuffix(strings.TrimSpace(strings.TrimPrefix(keyPart, "-")), ":"))
		keyName = strings.ToLower(keyName)
		if _, ok := translatableFMKeys[keyName]; !ok || len(strings.TrimSpace(value)) < minTextLength {
			result = append(result, line)
			continue
		}

		translated, ok := cacheGet(cache, value, targetLang)
		if ok {
			stats.CacheHits++
		} else {
			tr, err := callAPI(value, targetLang)
			if err != nil {
				return "", err
			}
			translated = postProcess(tr, targetLang)
			cachePut(cache, value, targetLang, translated)
			stats.CacheMisses++
			stats.APIRequests++
		}

		q := quote
		if q == "" {
			q = `"`
		}
		escaped := translated
		if q == `"` {
			escaped = strings.ReplaceAll(escaped, `"`, `\\"`)
		}
		if q == "'" {
			escaped = strings.ReplaceAll(escaped, `'`, `\\'`)
		}
		result = append(result, strings.TrimRight(keyPart, " ")+" "+q+escaped+q)
	}
	return strings.Join(result, "\n"), nil
}

func cacheKey(text, target string) string {
	base := fmt.Sprintf("%d:%s:en:%s:%d:%s", cacheVersion, modelName(), target, len(text), sha256Hex(strings.TrimSpace(normalizeSpace(text))))
	sum := sha256.Sum256([]byte(base))
	return hex.EncodeToString(sum[:])
}

func normalizeSpace(s string) string {
	return strings.Join(strings.Fields(s), " ")
}

func sha256Hex(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

func cacheGet(cache map[string]cacheEntry, text, target string) (string, bool) {
	entry, ok := cache[cacheKey(text, target)]
	if !ok || entry.R == "" {
		return "", false
	}
	return entry.R, true
}

func cachePut(cache map[string]cacheEntry, text, target, translation string) {
	cache[cacheKey(text, target)] = cacheEntry{R: translation, TS: time.Now().Unix()}
}

func postProcess(text, targetLang string) string {
	if targetLang == "vi" {
		text = regexp.MustCompile(`\s+([!?.,;:])`).ReplaceAllString(text, "$1")
		text = regexp.MustCompile(` {2,}`).ReplaceAllString(text, " ")
	}
	return strings.ReplaceAll(text, "] (", "](")
}

func translateOnePage(mdPath, lang string, cache map[string]cacheEntry, stats *stats, strict bool) (string, error) {
	md, err := os.ReadFile(mdPath)
	if err != nil {
		return "", err
	}
	text := string(md)
	fmText, body := extractFrontmatter(text)
	protectedBody, items := protect(body)
	if proseLength(protectedBody) < minTextLength {
		return text, nil
	}

	translatedBody, ok := cacheGet(cache, protectedBody, lang)
	if ok {
		stats.CacheHits++
	} else {
		stats.CacheMisses++
		tr, err := callAPI(protectedBody, lang)
		if err != nil {
			return "", err
		}
		translatedBody = postProcess(tr, lang)
		cachePut(cache, protectedBody, lang, translatedBody)
		stats.APIRequests++
	}

	restoredBody := restore(translatedBody, items)
	errs := validatePlaceholders(protectedBody, restoredBody)
	if len(errs) > 0 {
		for _, err := range errs {
			fmt.Printf("      VALIDATION: %s\n", err)
		}
		if strict {
			return "", errors.New(errs[0])
		}
		if fmText != "" {
			return fmText + restore(protectedBody, items), nil
		}
		return restore(protectedBody, items), nil
	}

	if fmText != "" {
		translatedFM, err := translateFrontmatter(fmText, lang, cache, stats)
		if err != nil {
			return "", err
		}
		return translatedFM + restoredBody, nil
	}
	return restoredBody, nil
}

func fixRelativePaths(md, sourceRel string) string {
	parts := strings.Split(filepath.ToSlash(sourceRel), "/")
	depth := len(parts) - 1
	if depth <= 0 {
		return md
	}
	extra := strings.Repeat("../", depth)
	md = regexp.MustCompile(`(?:from|require)\s*\(\s*['"](\.\.[^'"]+)['"]`).ReplaceAllStringFunc(md, func(match string) string {
		return strings.Replace(match, "../", extra, 1)
	})
	md = regexp.MustCompile(`import\s+[^'"\n]*from\s*['"](\.\.[^'"]+)['"]`).ReplaceAllStringFunc(md, func(match string) string {
		return strings.Replace(match, "../", extra, 1)
	})
	return md
}

func preValidatePage(mdPath string) []string {
	file, err := os.Open(mdPath)
	if err != nil {
		return nil
	}
	defer file.Close()
	issues := []string{}
	backtickCount := 0
	placeholderCount := 0
	buffer := make([]byte, 4096)
	for {
		n, err := file.Read(buffer)
		if n > 0 {
			text := string(buffer[:n])
			for i := 0; i < len(text)-2; i++ {
				if text[i] == '`' && text[i+1] == '`' && text[i+2] == '`' {
					backtickCount++
				}
			}
			placeholderCount += len(placeholderPattern.FindAllString(text, -1))
		}
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			break
		}
	}
	if placeholderCount > 0 {
		issues = append(issues, fmt.Sprintf("Already has %d placeholders", placeholderCount))
	}
	if backtickCount%2 != 0 {
		issues = append(issues, "Unmatched code blocks")
	}
	return issues
}

func findSourcePages(docsDir string, langDirs map[string]string) []string {
	var pages []string
	_ = filepath.WalkDir(docsDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			if d.Name() == ".vitepress" {
				return filepath.SkipDir
			}
			if _, ok := langDirs[d.Name()]; ok {
				return filepath.SkipDir
			}
			return nil
		}
		if filepath.Ext(path) == ".md" {
			if strings.Contains(filepath.Base(path), "[") {
				return nil
			}
			pages = append(pages, path)
		}
		return nil
	})
	sort.Strings(pages)
	return pages
}

func validateAPIKey() error {
	apiKey := strings.TrimSpace(os.Getenv("TRANSLATION_API_KEY"))
	if apiKey == "" {
		apiKey = strings.TrimSpace(os.Getenv("NVIDIA_API_KEY"))
	}
	if apiKey == "" {
		return errors.New("missing API key")
	}
	return nil
}

func modelName() string {
	if v := strings.TrimSpace(os.Getenv("TRANSLATION_MODEL")); v != "" {
		return v
	}
	return defaultModel
}

func baseURL() string {
	if v := strings.TrimSpace(os.Getenv("TRANSLATION_BASE_URL")); v != "" {
		return v
	}
	return defaultBaseURL
}

func timeoutSeconds() int {
	if v := strings.TrimSpace(os.Getenv("TRANSLATION_TIMEOUT")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return defaultTimeoutSeconds
}

func maxRetries() int {
	if v := strings.TrimSpace(os.Getenv("TRANSLATION_MAX_RETRIES")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			return n
		}
	}
	return defaultMaxRetries
}

func callAPI(text, targetLang string) (string, error) {
	apiKey := strings.TrimSpace(os.Getenv("TRANSLATION_API_KEY"))
	if apiKey == "" {
		apiKey = strings.TrimSpace(os.Getenv("NVIDIA_API_KEY"))
	}
	if apiKey == "" {
		return "", errors.New("missing API key")
	}

	payload := map[string]any{
		"model": modelName(),
		"messages": []map[string]string{
			{"role": "system", "content": fmt.Sprintf("Translate the following Markdown from English to %s. Translate only human-readable prose. Preserve all __PH_N__ placeholders exactly as they appear. Preserve Markdown formatting, structure, and meaning. Return only translated text.", languages[targetLang])},
			{"role": "user", "content": text},
		},
		"temperature": 1,
		"top_p":       0.95,
		"max_tokens":  MAX_TOKENS,
		"stream":      false,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}

	client := &http.Client{Timeout: time.Duration(timeoutSeconds()) * time.Second}
	retries := maxRetries()
	var lastErr error
	for attempt := 0; attempt <= retries; attempt++ {
		req, err := http.NewRequest("POST", strings.TrimSuffix(baseURL(), "/")+"/chat/completions", bytes.NewReader(body))
		if err != nil {
			return "", err
		}
		req.Header.Set("Authorization", "Bearer "+apiKey)
		req.Header.Set("Content-Type", "application/json")

		resp, err := client.Do(req)
		if err == nil {
			if resp.StatusCode < 400 {
				var result struct {
					Choices []struct {
						Message struct {
							Content string `json:"content"`
						} `json:"message"`
					} `json:"choices"`
				}
				decodeErr := json.NewDecoder(resp.Body).Decode(&result)
				resp.Body.Close()
				if decodeErr != nil {
					return "", decodeErr
				}
				if len(result.Choices) == 0 || strings.TrimSpace(result.Choices[0].Message.Content) == "" {
					return "", errors.New("empty translation")
				}
				return strings.TrimSpace(result.Choices[0].Message.Content), nil
			}
			status := resp.StatusCode
			b, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
			resp.Body.Close()
			lastErr = fmt.Errorf("API error %s: %s", resp.Status, strings.TrimSpace(string(b)))
			if status >= 400 && status < 500 && status != http.StatusRequestTimeout && status != http.StatusTooManyRequests {
				return "", lastErr
			}
		} else {
			lastErr = err
		}

		if attempt < retries {
			delay := time.Duration(2<<attempt) * time.Second
			fmt.Printf("      Retry %d/%d after %s (%s)\n", attempt+1, retries, delay, truncateError(lastErr))
			time.Sleep(delay)
		}
	}
	return "", fmt.Errorf("API failed after %d retries: %w", retries, lastErr)
}

func truncateError(err error) string {
	if err == nil {
		return "unknown error"
	}
	message := err.Error()
	if len(message) > 80 {
		return message[:80]
	}
	return message
}

const MAX_TOKENS = 8192

func fatal(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, "FATAL:", err)
		os.Exit(1)
	}
}
