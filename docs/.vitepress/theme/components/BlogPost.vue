<script setup lang="ts">
import { useData } from 'vitepress'

const { frontmatter } = useData()

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}
</script>

<template>
  <div class="blog-post">
    <header class="blog-post-header">
      <h1 class="blog-post-title">{{ frontmatter.title }}</h1>
      <time v-if="frontmatter.date" class="blog-post-date">{{ formatDate(frontmatter.date) }}</time>
      <p v-if="frontmatter.description" class="blog-post-desc">{{ frontmatter.description }}</p>
      <div v-if="frontmatter.tags && frontmatter.tags.length" class="blog-post-tags">
        <a
          v-for="tag in frontmatter.tags"
          :key="tag"
          :href="`/tags/${encodeURIComponent(tag)}/`"
          class="blog-post-tag"
        >#{{ tag }}</a>
      </div>
    </header>
    <div class="blog-post-content">
      <slot />
    </div>
  </div>
</template>
