---
title: "Goodbye WordPress, hello Automad!"
date: 2026-07-01
description: "My journey from WordPress to Automad CMS."
tags:
  - Tech
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



## Huh? Another CMS? Why not stay with WordPress?

That's because it's too overkill for me now, I realized I just need a flat-file CMS instead of a full-featured CMS like **Joomla!** or **WordPress**.

Another good reason is because it also matches my workflow, it's almost like WordPress with Gutenberg.

## Hey! I missed your tutorials, how am I gonna read them now????

I came prepared with the archive of the entire old site (exported to static HTML) and the XML files of Guides and Lifelogs.

You can download it at: [https://cloud.italiatroller.dpdns.org/s/raogUEOWAhMlmWI](https://cloud.italiatroller.dpdns.org/s/raogUEOWAhMlmWI)

Password for download is: t1(1$P0U\`zf&

*(OpenCloud/OCIS requires password protection)*

Bonus: You can import these XMLs to EmDash too