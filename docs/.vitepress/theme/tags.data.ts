import { createContentLoader } from 'vitepress'

interface Post {
  title: string
  date: string
  description: string
  url: string
  tags: string[]
  section: string
}

export default createContentLoader(['lifelogs/posts/*.md', 'guides/posts/*.md'], {
  transform(rawData): Post[] {
    return rawData
      .filter((page) => page.frontmatter.title)
      .sort((a, b) => +new Date(b.frontmatter.date) - +new Date(a.frontmatter.date))
      .map((page) => ({
        title: page.frontmatter.title,
        date: page.frontmatter.date,
        description: page.frontmatter.description,
        url: page.url,
        tags: page.frontmatter.tags || [],
        section: page.url.startsWith('/lifelogs') ? 'lifelogs' : 'guides'
      }))
  }
})
