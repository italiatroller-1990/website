---
layout: page
---

<script setup>
import { useData } from 'vitepress'
import TagPosts from '../.vitepress/theme/components/TagPosts.vue'

const { params } = useData()
</script>

<TagPosts :tag="params.tag" />
