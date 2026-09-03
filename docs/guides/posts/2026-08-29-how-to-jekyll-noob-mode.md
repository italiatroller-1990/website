---
title: "How to Jekyll - Noob mode"
date: 2026-08-29
description: "A beginner-friendly tutorial for setting up your first Jekyll site from scratch."
tags:
  - Web
  - Jekyll
---



# {{ $frontmatter.title }}

### {{ new Date($frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}



This is my first guide on Jekyll! Please comment on if you see misinformation.

## What is Jekyll?

[Jekyll](https://jekyllrb.com) is a static site generator made in Ruby. It commonly uses:

- Markdown for pages and posts

- Liquid for themes and templating

- Ruby and Bundler for dependency management, and Jekyll itself

## Requirements & recommendations

### 1. Tools

### Required

- Ruby, 3.1 is minimum, 3.4 recommended for current* version

- Reading skill for reading the documentation, RTFM is good, yes

- Liquid familiarity, which is not going to hurt your brain that much but it's gonna be clunky for YOU

- HTML, Markdown, YAML and Gemfile skills, which is too EZ

### Recommended

- LLM agent, can be used to assist with making your own theme, saves your sanity

- Helper scripts, you can find them on my website's [repository](https://github.com/italiatroller-1990/website) or any other source, because yes

- Your brain, obviously

### 2. Hosting

### Recommended

- GitHub Pages, Jekyll is served via Actions, basically the most reliable

- Cloudflare Pages, faster in site speed, but you're gonna wait for it to compile Ruby then install Jekyll and the dependecies, which will take way WAY longer than GitHub pages

- A home server, well don't get your hopes up when a power outage happens

- A VPS from a reliable provider, just don't get your credit card's balance to 0$

### 3. Domains

You can either use a domain you bought or subdomain you have. That's all, if you're unsure:

- Just get from a provider that works, or even better: bring your own DNS nameservers domains.

## Tips, tricks & notes

You should start reading the documentation, and follow along it. But do not blindly copy everything since you could cause issues with your source code.