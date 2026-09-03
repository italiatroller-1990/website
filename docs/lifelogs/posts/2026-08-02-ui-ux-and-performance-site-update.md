---
title: "UI, UX and performance site update!"
date: 2026-08-02
description: "Site update focusing on UI, UX, and performance improvements."
tags:
  - Site update
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



**Woohoo! Another website update!**

What is it this time???? I've got some news for you...

- UX: the GTranslate widget is moved to the right, which makes mobile UX better!
- UI: The comment section and GTranslate got some CSS styling... Finally!
- Performance: Now there is a load comments button, you can change the comments provider or press that button to load comments!