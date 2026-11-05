import { expect, test, type Page } from '@playwright/test'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'

async function login(page: Page, email: string, password: string) {
  await page.goto('/login')
  await page.getByLabel('Email address', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('button', { name: 'Set up authenticator' }).click()
  const secret = await page.locator('code').textContent()
  const python = fileURLToPath(new URL('../../backend/.venv/Scripts/python.exe', import.meta.url))
  const result = spawnSync(python, ['-c', 'import sys,pyotp;print(pyotp.TOTP(sys.stdin.read().strip()).now())'], { input: secret || '', encoding: 'utf8' })
  expect(result.status).toBe(0)
  await page.getByLabel('Authentication or recovery code').fill(result.stdout.trim())
  await page.getByRole('button', { name: 'Verify and continue' }).click()
  await page.getByRole('button', { name: /saved my codes/ }).click()
  await expect(page.getByRole('heading', { name: /Hello,/ })).toBeVisible()
}

test('CEO creates and downloads a verified backup; staff cannot access it', async ({ page, browser }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await login(page, process.env.E2E_EMAIL!, process.env.E2E_PASSWORD!)
  await page.getByRole('link', { name: 'Backup', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Backup', exact: true })).toBeVisible()
  await expect(page.getByText('Every Monday at 12:00 noon', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back up now' })).toBeEnabled()
  await page.getByRole('button', { name: 'Back up now' }).click()
  await expect(page.getByText('Verified', { exact: true })).toBeVisible({ timeout: 45_000 })
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /^Download backup from/ }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/\.dump\.enc$/)
  const bytes = await readFile((await download.path())!)
  const checksumPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: /^Download checksum from/ }).click()
  const checksum = await checksumPromise
  expect((await readFile((await checksum.path())!, 'utf8')).trim()).toBe(createHash('sha256').update(bytes).digest('hex'))
  await page.screenshot({ path: '../.verification/backups-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '../.verification/backups-mobile.png', fullPage: true })
  const staff = await browser.newContext()
  const staffPage = await staff.newPage()
  await login(staffPage, process.env.E2E_STAFF_EMAIL!, process.env.E2E_STAFF_PASSWORD!)
  await expect(staffPage.getByRole('link', { name: 'Backup', exact: true })).toHaveCount(0)
  expect((await staffPage.request.get('/api/backups')).status()).toBe(403)
  await staffPage.goto('/backups')
  await expect(staffPage).toHaveURL(/\/$/)
  await staff.close()
  expect(errors).toEqual([])
})
