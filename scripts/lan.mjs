import { networkInterfaces } from 'node:os'
import { parseEnv } from 'node:util'
import { pathToFileURL } from 'node:url'

// Enumerate the server's adapters; a browser's localhost refers to that browser's device.
export function lanAddresses(interfaces = networkInterfaces()) {
  const seen = new Set()
  return Object.entries(interfaces).flatMap(([name, addresses]) =>
    (addresses ?? []).filter(({ address, family, internal }) => {
      if (internal || family !== 'IPv4' || /^(127\.|169\.254\.|0\.)/.test(address) || seen.has(address)) return false
      seen.add(address)
      return true
    }).map(({ address }) => ({ name, address })))
}

export function lanEnvironment(dotenv, environment, addresses, port, apiPort) {
  const configured = { ...parseEnv(dotenv), ...environment }
  if ((configured.APP_ENV ?? 'development') !== 'development') {
    throw new Error('The LAN launcher requires APP_ENV=development. Use the HTTPS deployment for production.')
  }
  const origins = JSON.parse(configured.ALLOWED_ORIGINS ?? '["http://127.0.0.1:5173","http://localhost:5173"]')
  if (!Array.isArray(origins) || origins.some(origin => typeof origin !== 'string' || origin.includes('*'))) {
    throw new Error('ALLOWED_ORIGINS must be a JSON array of explicit origins.')
  }
  const localOrigins = ['127.0.0.1', 'localhost', ...addresses.map(({ address }) => address)]
    .map(address => `http://${address}:${port}`)
  return {
    ...environment,
    APP_ENV: 'development',
    // Plain HTTP on a LAN cannot use secure cookies. This applies only to child processes.
    COOKIE_SECURE: 'false',
    ALLOWED_ORIGINS: JSON.stringify([...new Set([...origins, ...localOrigins])]),
    PUBLIC_URL: `http://${addresses[0]?.address ?? '127.0.0.1'}:${port}`,
    API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`,
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  console.log(JSON.stringify(lanAddresses()))
}
