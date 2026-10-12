import { cpSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
const root = fileURLToPath(new URL('.', import.meta.url))
mkdirSync(`${root}dist`, { recursive: true })
cpSync(`${root}public`, `${root}dist`, { recursive: true })
console.log('MangoPoint request website built in dist/.')
