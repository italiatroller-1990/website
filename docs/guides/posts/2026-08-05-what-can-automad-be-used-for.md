---
title: "What can Automad be used for?"
date: 2026-08-05
description: "Exploring the various use cases and possibilities of the Automad CMS."
tags:
  - Automad CMS
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



- Portfolios
- Landing pages
- Blogs
- Software documentation
- Hardware documentation
- Shop site (technically with embedding iframes)
- Wikis (yes, I am serious)
- Simple corporate site
- Agency site
- Getting your Airtables
- Malware (freedom = can come with issues)
- Troll site