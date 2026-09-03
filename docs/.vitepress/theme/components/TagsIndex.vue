<script setup lang="ts">
import { computed } from 'vue'
import { data as posts } from '../tags.data.ts'

const formatDate = (dateStr: string) => {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}

const tags = computed(() => {
  const map = new Map<string, { count: number; posts: typeof posts }>()
  for (const post of posts) {
    for (const tag of post.tags) {
      if (!map.has(tag)) {
        map.set(tag, { count: 0, posts: [] })
      }
      const entry = map.get(tag)!
      entry.count++
      entry.posts.push(post)
    }
  }
  return Array.from(map.entries())
    .sort((a, b) => b[1].count - a[1].count)
    .map(([tag, data]) => ({ tag, ...data }))
})

const featuredTag = computed(() => tags.value[0] || null)
</script>

<template>
  <div class="tags-page">
    <div v-if="featuredTag" class="tag-featured-post">
      <h3>Featured: #{{ featuredTag.tag }}</h3>
      <p class="tag-featured-desc">{{ featuredTag.posts[0].description }}</p>
      <a :href="featuredTag.posts[0].url" class="blog-card-title">{{ featuredTag.posts[0].title }}</a>
      <time v-if="featuredTag.posts[0].date" class="blog-card-date">{{ formatDate(featuredTag.posts[0].date) }}</time>
    </div>
    <div class="tags-grid">
      <a
        v-for="item in tags"
        :key="item.tag"
        :href="`/tags/${encodeURIComponent(item.tag)}/`"
        class="tag-card"
      >
        <span class="tag-card-name">#{{ item.tag }}</span>
        <span class="tag-card-count">{{ item.count }} {{ item.count === 1 ? 'post' : 'posts' }}</span>
      </a>
    </div>
  </div>
</template>
