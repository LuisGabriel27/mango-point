import http from 'node:http'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('./dist/', import.meta.url))
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml' }
const port = Number(process.env.PORT || 8088)
const server = http.createServer(async (request, response) => {
  try {
    if (!['GET', 'HEAD'].includes(request.method)) { response.writeHead(405); response.end(); return }
    const url = new URL(request.url, 'http://localhost')
    const name = decodeURIComponent(url.pathname) === '/' ? 'index.html' : decodeURIComponent(url.pathname).slice(1)
    const filename = path.resolve(root, name)
    const relative = path.relative(root, filename)
    if (relative.startsWith('..') || path.isAbsolute(relative)) { response.writeHead(403); response.end(); return }
    const content = await readFile(filename)
    response.writeHead(200, { 'Content-Type': types[path.extname(filename)] || 'application/octet-stream', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' })
    response.end(request.method === 'HEAD' ? undefined : content)
  } catch { response.writeHead(404); response.end('Page not found.') }
})
server.listen(port, '127.0.0.1', () => console.log(`Local: http://127.0.0.1:${port}`))
