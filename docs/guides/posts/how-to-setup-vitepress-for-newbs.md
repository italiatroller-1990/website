---
title: How to setup VitePress for newbs
date: 2026-09-03
description: "A beginner's guide to setting up VitePress for the first time."
tags:
  - VitePress
  - Web
  - Tech
---

# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

<div v-if="$frontmatter.tags" class="blog-post-tags">
  <a v-for="tag in $frontmatter.tags" :key="tag" :href="`/tags/${encodeURIComponent(tag)}/`" class="blog-post-tag">#{{ tag }}</a>
</div>

# Welcome to this VitePress guide for newbies! This guide will probably cover:

- Dependecies before installing VitePress

- Installing and initializing VitePress

- Recommended template

- Tool recommendations

## 1. Dependecies

For VitePress, you're gonna need:

- Node.js 22 or higher

- A package manager for Node.js, like `npm`, `pnpm`, `yarn`, ...etc

You can get these from your package manager or from Node.js' website.

Package manager example because yes:

::: details Fedora:

```sh
# Install Node.js 22 and npm
sudo dnf install nodejs22 npm
```

:::

::: details Debian/Ubuntu:

```sh
# Install Node.js and npm
sudo apt install nodejs npm
```

:::

## 2. Installing and initializing VitePress

## 2.1 Installing VitePress, obviously

From the docs, you can install VitePress using Node.js package managers:

For most users, use `npm`:

```sh
npm add -D vitepress@next
```

## 2.2 Initializing VitePress

Initialize VitePress with `npx vitepress init`:

```sh
npx vitepress init
```

## 3. Recommended template for newbs

When initializing VitePress, you should use Default theme + CSS customization, this makes sure that you won't have to create a completely new theme while allowing you to customize with plain CSS rather than Sass or Tailwind!

## 4. Recommended tools

- Visual Studio Code/Code - OSS/VSCodium
    - Best IDE for Node.js currently, adds features like built-in browser and debugging using GUI.

- Coding agents
    - Just for assistance for various things for your site!