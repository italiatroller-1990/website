import { createContentLoader } from 'vitepress'

function extractFirstImage(src: string | undefined): string | null {
  if (!src) return null
  const match = src.match(/!\[.*?\]\(([^)]+\.(webp|jpg|jpeg|png|gif|avif))\)|<img[^>]+src="([^"]+\.(webp|jpg|jpeg|png|gif|avif))"/i)
  return match ? (match[1] || match[3]) : null
}

export default createContentLoader('guides/posts/*.md', {
  transform(rawData) {
    return rawData
      .filter((page) => page.frontmatter.title)
      .sort((a, b) => +new Date(b.frontmatter.date) - +new Date(a.frontmatter.date))
      .map((page) => ({
        title: page.frontmatter.title,
        date: page.frontmatter.date,
        description: page.frontmatter.description,
        url: page.url,
        tags: page.frontmatter.tags || [],
        image: page.frontmatter.image || extractFirstImage(page.src)
      }))
  }
})
