---
title: "I'm switching to Jekyll!"
date: 2026-08-28
description: "Why I decided to migrate my site from Automad to Jekyll."
tags:
  - Web
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



## Long time no see!

I am switching to Jekyll, and that's due to flexibility! And well, how is it right now?

While you can, I also have my older Automad blogs imported by using an LLM to fetch my lifelogs and guides. Which means you get to read it!

## Reasons

The reason why I'm switching to Jekyll is:

- GitHub

- Reducing stress on my homelab to make room for Continuwuity

That's all! C'yall later on lifelogs and guides!