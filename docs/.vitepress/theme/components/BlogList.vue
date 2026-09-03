<script setup lang="ts">
import { computed } from 'vue'
import { data as lifelogs } from '../lifelogs.data.ts'
import { data as guides } from '../guides.data.ts'

const props = defineProps<{
  folder: string
}>()

const posts = computed(() => {
  return props.folder === 'lifelogs' ? lifelogs : guides
})

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}
</script>

<template>
  <div class="blog-list">
    <div v-if="posts.length === 0" class="blog-empty">
      <p>No posts yet. Check back soon!</p>
    </div>
    <a
      v-for="post in posts"
      :key="post.url"
      :href="post.url"
      class="blog-card"
    >
      <img v-if="post.image" :src="post.image" alt="" class="blog-card-image" loading="lazy" />
      <h2 class="blog-card-title">{{ post.title }}</h2>
      <time v-if="post.date" class="blog-card-date">{{ formatDate(post.date) }}</time>
      <p v-if="post.description" class="blog-card-desc">{{ post.description }}</p>
      <div v-if="post.tags && post.tags.length" class="blog-card-tags">
        <a
          v-for="tag in post.tags"
          :key="tag"
          :href="`/tags/${encodeURIComponent(tag)}/`"
          class="blog-card-tag"
          @click.stop
        >#{{ tag }}</a>
      </div>
    </a>
  </div>
</template>
