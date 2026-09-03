---
title: My comparison on SSGs since I switched to VitePress
date: 2026-09-03
description: "A comparison of SSGs and CMSes after switching to VitePress."
tags:
  - Web
  - VitePress
---

# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>

I just switched to VitePress and the experience is incredible, easy formatting, hero sections, ...all I needed!

...and it's so good that I could say that it's the best SSG ever too!

But, for fairness, I'm going to make a comparison table

## SSG / CMS Comparison

| SSG / CMS     | Speed            | User-Friendliness | Flexibility      | Framework/lang   |
| :------------ | :--------------- | :---------------- | :--------------- | :----------------|
| **WordPress** | 🟡 Medium        | 🟢 Very friendly  | 🟢 Very flexible | PHP and JS       |
| **Automad**   | 🟢 Fast          | 🟢 Very friendly  | 🟡 Limited       | PHP, JS and UIKit|
| **Jekyll**    | 🟢 Pretty fast   | 🟡 Medium         | 🟢 Very flexible | Ruby             |
| **VitePress** | 🟢 **VERY fast** | 🟢 Friendly       | 🟢 Very flexible | Vue + Vite       |
