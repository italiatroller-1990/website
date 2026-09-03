<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { data as posts } from '../tags.data.ts'

const searchQuery = ref('')
const debouncedSearchQuery = ref('')
const timeoutId = ref<number | null>(null)

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

const filteredTags = computed(() => {
  if (!debouncedSearchQuery.value) return tags.value
  
  const search = debouncedSearchQuery.value.toLowerCase()
  return tags.value.filter(([tag, { count, posts: tagPosts }]) => {
    const matchesTag = tag.toLowerCase().includes(search)
    const matchesPost = tagPosts.some(post => 
      post.title.toLowerCase().includes(search) ||
      post.description.toLowerCase().includes(search)
    )
    return matchesTag || matchesPost
  })
})

const updateSearch = () => {
  if (searchQuery.value !== '') {
    if (timeoutId.value) {
      clearTimeout(timeoutId.value)
    }
    timeoutId.value = setTimeout(() => {
      debouncedSearchQuery.value = searchQuery.value
    }, 300)
  } else {
    debouncedSearchQuery.value = ''
    if (timeoutId.value) {
      clearTimeout(timeoutId.value)
      timeoutId.value = null
    }
  }
}

onMounted(() => {
  debouncedSearchQuery.value = searchQuery.value
})

onUnmounted(() => {
  if (timeoutId.value) {
    clearTimeout(timeoutId.value)
  }
})
</script>

<template>
  <div class="tags-page">
    <div class="tag-search-wrapper">
      <input
        v-model="searchQuery"
        type="text"
        class="tag-search-input"
        placeholder="Search tags or content..."
        @input="updateSearch"
      />
    </div>
    <div v-if="searchQuery && filteredTags.length === 0" class="blog-empty">
      <p>No tags found matching "{{ searchQuery }}"</p>
    </div>
    <div v-else>
      <div v-if="filteredTags.length > 0" class="tag-featured-post">
        <h3>Featured: #{{ filteredTags[0].tag }}</h3>
        <p class="tag-featured-desc">{{ filteredTags[0].posts[0].description }}</p>
        <a :href="filteredTags[0].posts[0].url" class="blog-card-title">{{ filteredTags[0].posts[0].title }}</a>
        <time v-if="filteredTags[0].posts[0].date" class="blog-card-date">{{ formatDate(filteredTags[0].posts[0].date) }}</time>
      </div>
      <div class="tags-grid">
        <a
          v-for="item in filteredTags"
          :key="item.tag"
          :href="`/tags/${encodeURIComponent(item.tag)}/`"
          class="tag-card"
        >
          <span class="tag-card-name">#{{ item.tag }}</span>
          <span class="tag-card-count">{{ item.count }} {{ item.count === 1 ? 'post' : 'posts' }}</span>
        </a>
      </div>
    </div>
  </div>
</template>
