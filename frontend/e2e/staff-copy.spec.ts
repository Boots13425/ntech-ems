import { expect, test } from '@playwright/test'
import { createServer, type Server } from 'node:http'
import { readFile } from 'node:fs/promises'
import { resolve, extname } from 'node:path'

let server: Server
let origin: string
const password = 'Clipboard-regression-test-123'
test.beforeAll(async () => {
  const root = resolve('dist')
  server = createServer(async (request, response) => {
    const pathname = new URL(request.url!, 'http://localhost').pathname
    const file = pathname.startsWith('/assets/') ? resolve(root, `.${pathname}`) : resolve(root, 'index.html')
    try {
      response.setHeader('Content-Type', extname(file) === '.js' ? 'application/javascript' : extname(file) === '.css' ? 'text/css' : 'text/html')
      response.end(await readFile(file))
    } catch { response.writeHead(404).end() }
  })
  await new Promise<void>(done => server.listen(0, '127.0.0.1', done))
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('Missing server address')
  origin = `http://127.0.0.1:${address.port}`
})
test.afterAll(async () => { await new Promise<void>((done, reject) => server.close(error => error ? reject(error) : done())) })

for (const mode of ['unavailable', 'denied'] as const) {
  test(`staff password copies when Clipboard API is ${mode}`, async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin })
    await page.addInitScript(mode => {
      // Keep the real clipboard reader to verify the OS clipboard, not a mock.
      const read = navigator.clipboard.readText.bind(navigator.clipboard)
      Object.defineProperty(window, 'readTestClipboard', { value: read })
      Object.defineProperty(navigator, 'clipboard', { value: mode === 'unavailable' ? undefined : { writeText: () => Promise.reject(new DOMException('Denied', 'NotAllowedError')) } })
    }, mode)
    const user = { id: 'ceo', full_name: 'Test CEO', email: 'ceo@example.org', roles: ['CEO'], responsibilities: [], permissions: ['staff.manage', 'staff.read'], is_active: true, mfa_enabled: true, must_change_password: false, session_state: 'authenticated' }
    await page.route('**/api/**', async route => {
      const pathname = new URL(route.request().url()).pathname
      let data: unknown = {}
      if (pathname === '/api/auth/me') data = user
      if (pathname === '/api/staff') data = route.request().method() === 'POST' ? { ...user, ...route.request().postDataJSON(), temporary_password: password } : { items: [], total: 0, page: 1, page_size: 20 }
      await route.fulfill({ json: data })
    })
    await page.goto(`${origin}/staff`)
    await page.getByRole('button', { name: 'Add team member' }).click()
    await page.getByLabel('Full name', { exact: true }).fill('New Staff')
    await page.getByLabel('Email address', { exact: true }).fill('staff@example.org')
    await page.getByRole('button', { name: 'Create account', exact: true }).click()
    await page.getByRole('button', { name: 'Copy temporary password' }).click()
    await expect(page.getByText('Password copied.', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => (window as unknown as { readTestClipboard: () => Promise<string> }).readTestClipboard())).toBe(password)
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
}
