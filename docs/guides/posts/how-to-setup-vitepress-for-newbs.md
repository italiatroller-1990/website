---
title: How to setup VitePress for newbs
date: 2026-09-03
description: "A beginner's guide to setting up VitePress for the first time."
tags:
  - VitePress
  - Web
  - Tech
---

# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>

