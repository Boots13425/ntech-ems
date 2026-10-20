// Verify the interface, its API proxy, and the origins needed by browsers before reusing a listener.
export async function inspectRunningLan(port, addresses) {
  const localUrl = `http://127.0.0.1:${port}`
  try {
    const [page, health] = await Promise.all([
      fetch(localUrl, { signal: AbortSignal.timeout(2000) }),
      fetch(`${localUrl}/api/health`, { signal: AbortSignal.timeout(2000) }),
    ])
    const [html, readiness] = await Promise.all([page.text(), health.json()])
    if (!page.ok || !/<title>\s*NTECH EMS\b/i.test(html) || !health.ok
      || readiness.application !== 'NTECH EMS' || readiness.status !== 'ready') {
      return { ready: false, reason: 'The existing listener is not a healthy NTECH EMS interface and API.' }
    }

    const origins = [...new Set([localUrl, ...addresses.map(({ address }) => `http://${address}:${port}`)])]
    const checks = await Promise.all(origins.map(async origin => {
      try {
        // Vite answers OPTIONS itself, so check the API's origin headers on a proxied health request.
        const response = await fetch(`${origin}/api/health`, {
          signal: AbortSignal.timeout(2000), headers: { Origin: origin },
        })
        const readiness = await response.json()
        return response.ok && response.headers.get('access-control-allow-origin') === origin
          && response.headers.get('access-control-allow-credentials') === 'true'
          && readiness.application === 'NTECH EMS' && readiness.status === 'ready'
      } catch { return false }
    }))
    if (!checks.every(Boolean)) {
      return { ready: false, reason: 'The existing interface is not reachable or does not allow requests from all current LAN addresses.' }
    }
    return { ready: true }
  } catch {
    return { ready: false, reason: 'The existing interface or its API proxy is not responding correctly.' }
  }
}
