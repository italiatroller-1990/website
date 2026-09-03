import { createContentLoader } from 'vitepress'

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
        tags: page.frontmatter.tags || []
      }))
  }
})
