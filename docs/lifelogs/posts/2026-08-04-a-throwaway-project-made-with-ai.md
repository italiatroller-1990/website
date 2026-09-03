---
title: "A throwaway project made with AI."
date: 2026-08-04
description: "Building a throwaway project entirely with AI assistance."
tags:
  - AI
  - LLM
  - Markdown
  - Tech
  - Web
  - WordPress
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



I made a throwaway project today with ChatGPT, and it works.

What kind of project exactly? A WXR (WordPress Extended RSS) to Markdown converter.

### How does it work?

After you export your WordPress pages and posts to an XML file, which is what WXR uses, you can upload the file to the converter.

The converter will do the job client-side:

- Read the XML
- Detect patterns that WordPress uses on the XML, e.g `wp-paragraph`
- Detect tables
- Detect categories
- Then convert it to Markdown
- Zip them (uses no external Node.js modules, just pure JS)

This tool is pretty useful for people who are going to switch from WordPress to a SSG or a flat-file CMS that needs a converted Markdown file, then paste it to their contents.

### What lang is it made?

Pure HTML, CSS and JS.

This tool is now available on:

[https://wxr-to-md.italiatroller.dpdns.org/](https://wxr-to-md.italiatroller.dpdns.org/)

Source code:

[https://git.italiatroller.dpdns.org/italiatroller/WXR-to-MD](https://git.italiatroller.dpdns.org/italiatroller/WXR-to-MD)