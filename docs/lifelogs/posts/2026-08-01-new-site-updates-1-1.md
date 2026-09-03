---
title: "New site updates!1!!!!!1"
date: 2026-08-01
description: "New updates and improvements to the site."
tags:
  - Site update
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



## Yep, this site went from barebones, to being actually nice to see

### Changelog

- Added Giscus + Intense Debate comment selectors!
- Added GTranslate, because I am too lazy to translate even for my native language (Vietnamese)
- FONT AWESOME!!!!!1!!!!!111!!!!!111!!!
- And font is now SUSE Mono!!1!1