---
title: "WordPress alternatives^2"
date: 2026-08-31
description: "Yep, another alternatives!!!"
tags:
  - CMS
  - Web
  - WordPress
  - Alternatives
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>



# This guide only focuses on blogging and e-commerce

Well, WordPress is still very widely used, the first alternative post is in my WordPress site archive, check this [blog post](/lifelog/old-blogs-ar/)!

Now, WordPress is feeling like... being replaced by something else by bloggers and some e-commerce companies. Which is quite reasonable, but in this guide, I will cover the alternatives that are popular by my personal opinions, not user reviews.

### 1. Automad

By far the easiest flat-file CMS I used, customizable themes, SEO, and essential website stuff included.

**BUT** Automad still have specific problems that can actually hurt some users and security:

- Custom HTML, CSS and JS may be flexible, but you can actually inject XSS, which can cause some security risks if you copy the code from non-verified sources

- Small ecosystem, yes, small ecosystem is pretty downgrading ngl

- v1 theme's footer on mobile makes my ADHD active

Score: 9/10

### 2. Joomla

More powerful than stock WordPress setup, the page builder is very flexible. I like it!

But the only thing left is database and plugins, which aren't that consistent...

Score: 7.5/10

### 3. Grav

Dude, what, this is more confusing to do than a fricking SSG... how tf do I add a pagelist!!?!?!?!?

Score: 5/10

### 4. Jekyll

It's a SSG, it generates sites statically.

It's easy to start with and it's very flexible. **BUT** wait:

- Liquid templating could get awkward!

Score: 9/10

### 5. Hugo

It's also a SSG, but it's very fast and lightweight. Downside is Go templates are very confusing...

Score: 8.5/10

That's all, folks!