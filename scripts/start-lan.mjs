import { spawn } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'
import { lanAddresses, lanEnvironment } from './lan.mjs'
import { inspectRunningLan } from './running-lan.mjs'

const root = fileURLToPath(new URL('../', import.meta.url))
const children = new Set()
let stopping = false

function stop(code = 0) {
  if (stopping) return
  stopping = true
  process.exitCode = code
  for (const child of children) {
    try { child.kill('SIGTERM') }
    catch (error) { console.error(`Could not stop process ${child.pid}: ${error.message}`); process.exitCode = 1 }
  }
}

function start(command, args, cwd, env) {
  const child = spawn(command, args, { cwd, env, stdio: 'inherit', windowsHide: true })
  children.add(child)
  child.on('error', error => { console.error(error.message); stop(1) })
  child.on('exit', code => {
    children.delete(child)
    if (!stopping) {
      console.error(`${command} stopped; closing the LAN servers.`)
      stop(code || 1)
    }
  })
  return child
}

function portNumber(value) {
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65535) throw new Error(`Invalid port: ${value}`)
  return Number(value)
}

async function checkPort(port, host) {
  await new Promise((accept, reject) => {
    const server = createServer()
    server.once('error', () => reject(new Error(`Port ${port} is unavailable. Stop the existing server or choose another port.`)))
    server.listen({ port, host, exclusive: true }, () => server.close(accept))
  })
}

async function waitForApi(child, port) {
  const deadline = Date.now() + 30_000
  while (Date.now() < deadline && !stopping) {
    if (child.exitCode !== null) throw new Error('The API stopped before becoming ready.')
    try {
      const response = await fetch(`http://127.0.0.1:${port}/api/health`, { signal: AbortSignal.timeout(2000) })
      if (response.ok) return
    } catch { /* Allow the API time to start. */ }
    await new Promise(accept => setTimeout(accept, 250))
  }
  if (!stopping) throw new Error('API readiness timed out. Check PostgreSQL, backend/.env, and database migrations.')
}

async function main() {
  const { values } = parseArgs({ options: {
    preview: { type: 'boolean' }, urls: { type: 'boolean' },
    port: { type: 'string' }, 'api-port': { type: 'string', default: '8000' },
  } })
  const port = portNumber(values.port ?? (values.preview ? '4173' : '5173'))
  const apiPort = portNumber(values['api-port'])
  if (port === apiPort) throw new Error('The frontend and API need different ports.')
  const addresses = lanAddresses()
  console.log(`\nNTECH EMS - ${values.preview ? 'build preview' : 'development'} LAN access`)
  console.log(`  This computer: http://127.0.0.1:${port}`)
  for (const { name, address } of addresses) console.log(`  ${name}: http://${address}:${port}`)
  if (!addresses.length) console.warn('No LAN IPv4 address found. Connect to Wi-Fi/Ethernet and restart this command.')
  if (values.urls) return

  const python = resolve(root, process.platform === 'win32' ? 'backend/.venv/Scripts/python.exe' : 'backend/.venv/bin/python')
  const vite = resolve(root, 'frontend/node_modules/vite/bin/vite.js')
  const dotenv = resolve(root, 'backend/.env')
  if (!existsSync(python)) throw new Error('Create backend/.venv and install the backend dependencies first (see README.md).')
  if (!existsSync(vite)) throw new Error('Install frontend dependencies first: cd frontend and run npm ci.')
  if (!existsSync(dotenv)) throw new Error('Configure backend/.env first (see README.md).')
  if (values.preview && !existsSync(resolve(root, 'frontend/dist/index.html'))) throw new Error('Build the frontend first: cd frontend and run npm run build.')
  const env = lanEnvironment(readFileSync(dotenv, 'utf8'), process.env, addresses, port, apiPort)
  try {
    await checkPort(port, '0.0.0.0')
  } catch (error) {
    const running = await inspectRunningLan(port, addresses)
    if (running.ready) {
      console.log(`\nNTECH EMS is already running on port ${port}. Its interface and API are ready for LAN access.`)
      console.log('Using the existing instance; no additional servers were started. Keep its original terminal open.')
      console.log(`--api-port ${apiPort} applies only when starting a new instance; the existing API connection is unchanged.`)
      return
    }
    throw new Error(`${error.message}\n${running.reason}\nIf this is your frontend, stop it in its original terminal with Ctrl+C, then run this command again.`)
  }
  await checkPort(apiPort, '127.0.0.1')
  console.log('\nStarting API (including campaign delivery and reply checking) and interface. Keep this terminal open; Ctrl+C stops them.')
  const api = start(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(apiPort)], resolve(root, 'backend'), env)
  await waitForApi(api, apiPort)
  if (stopping) return
  start(process.execPath, [vite, ...(values.preview ? ['preview'] : []), '--host', '0.0.0.0', '--port', String(port), '--strictPort'], resolve(root, 'frontend'), env)
}

process.on('SIGINT', () => stop())
process.on('SIGTERM', () => stop())
main().catch(error => { console.error(error.message); stop(1) })
