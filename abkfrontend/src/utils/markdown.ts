function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderInline(raw: string): string {
  const codes: string[] = []
  const marked = raw.replace(/`([^`\n]+)`/g, (_match, code: string) => {
    codes.push(escapeHtml(code))
    return `\u0000${codes.length - 1}\u0000`
  })
  let html = escapeHtml(marked)
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)"]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  )
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
  html = html.replace(/(^|[^\*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
  html = html.replace(/\u0000(\d+)\u0000/g, (_match, index: string) => `<code>${codes[Number(index)]}</code>`)
  return html
}

function isList(line: string, kind: 'ul' | 'ol'): boolean {
  return kind === 'ul' ? /^[-*]\s+/.test(line) : /^\d+\.\s+/.test(line)
}

function listItem(line: string, kind: 'ul' | 'ol'): string {
  const text = kind === 'ul' ? line.replace(/^[-*]\s+/, '') : line.replace(/^\d+\.\s+/, '')
  return `<li>${renderInline(text)}</li>`
}

/** 把模型输出的 Markdown 转成安全 HTML。先转义原文，再只生成已知标签。 */
export function renderMarkdown(source: string): string {
  const lines = (source || '').replace(/\r\n/g, '\n').split('\n')
  const blocks: string[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    if (line.trim() === '') {
      index += 1
      continue
    }
    if (line.startsWith('```')) {
      const code: string[] = []
      index += 1
      while (index < lines.length && !lines[index].startsWith('```')) {
        code.push(lines[index])
        index += 1
      }
      if (index < lines.length) index += 1
      blocks.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`)
      continue
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      blocks.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      index += 1
      continue
    }

    if (isList(line, 'ul') || isList(line, 'ol')) {
      const kind = isList(line, 'ul') ? 'ul' : 'ol'
      const items: string[] = []
      while (index < lines.length && isList(lines[index], kind)) {
        items.push(listItem(lines[index], kind))
        index += 1
      }
      blocks.push(`<${kind}>${items.join('')}</${kind}>`)
      continue
    }

    const paragraph: string[] = []
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].startsWith('```') &&
      !/^(#{1,3})\s+/.test(lines[index]) &&
      !isList(lines[index], 'ul') &&
      !isList(lines[index], 'ol')
    ) {
      paragraph.push(renderInline(lines[index]))
      index += 1
    }
    blocks.push(`<p>${paragraph.join('<br>')}</p>`)
  }

  return blocks.join('')
}
