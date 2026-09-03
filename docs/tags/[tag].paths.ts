import fs from 'node:fs'
import path from 'node:path'

export default {
  paths() {
    const tags = new Set<string>()
    const dirs = ['lifelogs/posts', 'guides/posts']

    for (const dir of dirs) {
      const dirPath = path.resolve(__dirname, '..', dir)
      if (!fs.existsSync(dirPath)) continue
      const files = fs.readdirSync(dirPath).filter((f) => f.endsWith('.md'))
      for (const file of files) {
        const content = fs.readFileSync(path.join(dirPath, file), 'utf-8')
        const match = content.match(/^tags:\s*\n((?:\s*-\s*.+\n?)+)/m)
        if (match) {
          const tagLines = match[1].split('\n').filter((l) => l.trim())
          for (const line of tagLines) {
            const tag = line.replace(/^\s*-\s*/, '').trim()
            if (tag) tags.add(tag)
          }
        }
      }
    }

    return Array.from(tags).map((tag) => ({
      params: { tag }
    }))
  }
}
