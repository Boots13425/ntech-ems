import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'node:http'
import { lanAddresses, lanEnvironment } from './lan.mjs'
import { inspectRunningLan } from './running-lan.mjs'

test('discovers Wi-Fi and Ethernet IPv4 addresses while excluding unusable addresses and duplicates', () => {
  const entry = (address, internal = false, family = 'IPv4') => ({ address, internal, family })
  assert.deepEqual(lanAddresses({
    Loopback: [entry('127.0.0.1', true), entry('::1', true, 'IPv6')],
    'Wi-Fi': [entry('192.168.1.20'), entry('fe80::1', false, 'IPv6')],
    Ethernet: [entry('10.0.0.12'), entry('169.254.1.2')],
    Duplicate: [entry('192.168.1.20')], Missing: undefined,
  }), [{ name: 'Wi-Fi', address: '192.168.1.20' }, { name: 'Ethernet', address: '10.0.0.12' }])
})

test('uses current IP and port, preserves configured origins and never writes secrets to frontend variables', () => {
  const env = lanEnvironment('ALLOWED_ORIGINS=["https://office.example"]\nCOOKIE_SECURE=true\nDATABASE_URL=private',
    { EXISTING: 'kept' }, [{ address: '192.168.1.20' }], 5200, 8100)
  assert.deepEqual(JSON.parse(env.ALLOWED_ORIGINS), [
    'https://office.example', 'http://127.0.0.1:5200', 'http://localhost:5200', 'http://192.168.1.20:5200',
  ])
  assert.equal(env.API_PROXY_TARGET, 'http://127.0.0.1:8100')
  assert.equal(env.PUBLIC_URL, 'http://192.168.1.20:5200')
  assert.equal(env.COOKIE_SECURE, 'false')
  assert.equal(env.EXISTING, 'kept')
  assert.equal(env.DATABASE_URL, undefined)
})

test('honors environment overrides and redetects changed addresses on the next start', () => {
  const inherited = { ALLOWED_ORIGINS: '["https://override.example"]', DATABASE_URL: 'test-db' }
  const env = lanEnvironment('ALLOWED_ORIGINS=["https://file.example"]', inherited, [{ address: '10.0.0.15' }], 4173, 8001)
  assert.deepEqual(JSON.parse(env.ALLOWED_ORIGINS), [
    'https://override.example', 'http://127.0.0.1:4173', 'http://localhost:4173', 'http://10.0.0.15:4173',
  ])
  assert.equal(env.DATABASE_URL, 'test-db')
  assert.equal(env.PUBLIC_URL, 'http://10.0.0.15:4173')
  assert.equal(lanEnvironment('', {}, [], 5173, 8000).PUBLIC_URL, 'http://127.0.0.1:5173')
})

test('refuses production settings and wildcard or malformed origin configuration', () => {
  for (const dotenv of ['APP_ENV=production', 'ALLOWED_ORIGINS=["*"]', 'ALLOWED_ORIGINS={}', 'ALLOWED_ORIGINS=[1]']) {
    assert.throws(() => lanEnvironment(dotenv, {}, [], 5173, 8000))
  }
  assert.throws(() => lanEnvironment('', { APP_ENV: 'production' }, [], 5173, 8000))
})

async function runningFrontend(t, { title = 'NTECH EMS', healthy = true, allowedOrigins = true, application = 'NTECH EMS' } = {}) {
  const server = createServer((request, response) => {
    if (request.url === '/api/health') {
      const origin = request.headers.origin
      const allowOrigin = typeof allowedOrigins === 'function' ? allowedOrigins(origin) : allowedOrigins
      response.writeHead(healthy ? 200 : 503, {
        'content-type': 'application/json',
        ...(origin && allowOrigin ? { 'access-control-allow-origin': origin, 'access-control-allow-credentials': 'true' } : {}),
      })
      response.end(JSON.stringify({ application, status: healthy ? 'ready' : 'not_ready' }))
    } else response.end(`<html><title>${title}</title></html>`)
  })
  await new Promise(resolve => server.listen(0, '0.0.0.0', resolve))
  t.after(() => new Promise((resolve, reject) => {
    server.close(error => error ? reject(error) : resolve())
    server.closeAllConnections()
  }))
  return server.address().port
}

test('recognizes an existing healthy LAN frontend and its API instead of treating the occupied port as an error', async t => {
  const port = await runningFrontend(t)
  assert.deepEqual(await inspectRunningLan(port, [{ address: '127.0.0.2' }]), { ready: true })
})

test('does not reuse an unrelated frontend even if it proxies the NTECH API', async t => {
  const port = await runningFrontend(t, { title: 'Another application' })
  assert.equal((await inspectRunningLan(port, [])).ready, false)
})

test('does not reuse an unhealthy or unrelated API', async t => {
  for (const options of [{ healthy: false }, { application: 'Another API' }]) {
    const port = await runningFrontend(t, options)
    assert.equal((await inspectRunningLan(port, [])).ready, false)
  }
})

test('does not claim LAN readiness when browser origin checks would reject login', async t => {
  const port = await runningFrontend(t, { allowedOrigins: origin => !origin?.includes('127.0.0.2') })
  assert.equal((await inspectRunningLan(port, [{ address: '127.0.0.2' }])).ready, false)
})

test('handles a frontend that is not running', async () => {
  const server = createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  assert.equal((await inspectRunningLan(port, [])).ready, false)
})
