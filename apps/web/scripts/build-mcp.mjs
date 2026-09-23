import { build } from 'esbuild'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../../../', import.meta.url))
const result = await build({
  absWorkingDir: root,
  entryPoints: ['services/agent/zagent/job_ui/main.tsx'],
  nodePaths: [path.join(root, 'apps/web/node_modules')],
  bundle: true, write: false, minify: true, format: 'iife', target: 'es2022',
  jsx: 'automatic', loader: { '.woff2': 'dataurl' },
  define: { 'process.env.NODE_ENV': '"production"' },
})
const template = await readFile(path.join(root, 'services/agent/zagent/job_ui/index.html'), 'utf8')
const script = result.outputFiles[0].text.replaceAll('</script', '<\\/script')
const directory = path.join(root, 'services/agent/zagent/resources')
await mkdir(directory, { recursive: true })
await writeFile(path.join(directory, 'jobs.html'), template.replace('<!--APP-->', () => `<script>${script}</script>`))
console.log('Built jobs MCP App resource')