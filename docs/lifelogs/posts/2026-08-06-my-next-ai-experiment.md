---
title: "My next AI experiment"
date: 2026-08-06
description: "Planning my next experiment with AI and language models."
tags:
  - AI
  - LLM
  - Tech
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



## Time for LLM experiments....

And that's especially on free models, I'm gonna see how free models can handle these project scales:

- Small scale (WXR-to-MD and Matrixrraria)
- Medium scale (AISlopCMS)
- Large scale, Rust (Prowser, W.I.P currently)

I will be pausing game development for a while, and learn what I learned