---
title: "Should you use AI on your project?"
date: 2026-08-04
description: "When to use AI in your projects and when to avoid it."
tags:
  - BSD
  - Bash
  - Linux
  - Programming
  - Tech
  - Unix
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



## Depends

Here's the awnsers you will need

YES:

- Throwaway project
- Assistance
- Code fixing
- Reviewing simple code
- Small functions
- Quick fixes
- Website speed boost from existing code by optimizing it

NO:

- Vibe coding
- Large functions that are critical
- Code to database functions, depending on models