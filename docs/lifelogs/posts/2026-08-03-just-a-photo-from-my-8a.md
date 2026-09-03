---
title: "Just a photo from my 8a, with some grainiess from zooming!"
date: 2026-08-03
description: "A grainy zoomed-in photo from my Samsung Galaxy 8a."
tags:
  - Photography
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



Buildings in Ninh Binh, captured on the Google Pixel 8a by me with GrapheneOS camera app with 2 - 3x digital zoom.

<img src="/assets/images/lifelog/just-a-photo-from-my-8a/image-1785938220354.webp" alt="Buildings in Ninh Binh, captured on Google Pixel 8a" width="1600" height="900" loading="lazy">