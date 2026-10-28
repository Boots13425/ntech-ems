import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ErrorState, Loading } from '@/components/shared'
import { api, ApiError, send } from '@/lib/api'

type Configuration = {
  host: string; port: number; security: 'starttls' | 'tls' | 'none'
  sender_name: string; sender_email: string; username: string
  password_configured: boolean; updated_at: string | null; saved: boolean
  imap_host: string; imap_port: number; imap_username: string; imap_password_configured: boolean; hourly_limit: number
}
const queryKey = ['email-configuration']

function ConfigurationForm({ initial }: { initial: Configuration }) {
  const client = useQueryClient()
  const [form, setForm] = useState(initial)
  const [password, setPassword] = useState('')
  const [imapPassword, setImapPassword] = useState('')
  const [clearPassword, setClearPassword] = useState(false)
  const [recipient, setRecipient] = useState('')
  const [result, setResult] = useState('')
  const dirty = JSON.stringify(form) !== JSON.stringify(initial) || !!password || !!imapPassword || clearPassword
  const save = useMutation({
    mutationFn: () => send<Configuration>('/settings/email', {
      host: form.host, port: form.port, security: form.security, sender_name: form.sender_name,
      sender_email: form.sender_email, username: form.username, password: password || null,
      clear_password: clearPassword, updated_at: initial.updated_at,
      imap_host: form.imap_host || null, imap_port: form.imap_port, imap_username: form.imap_username,
      imap_password: imapPassword || null, hourly_limit: form.hourly_limit,
    }, 'PUT'),
    onSuccess: data => {
      setPassword(''); setImapPassword(''); setClearPassword(false)
      client.setQueryData(queryKey, data)
      toast.success('Email configuration saved')
    },
    onError: error => toast.error(error instanceof ApiError && error.errors?.length
      ? error.errors.map(item => `${item.field.replaceAll('_', ' ')}: ${item.message}`).join('; ')
      : error.message),
  })
  const test = useMutation({
    mutationFn: (kind: 'connection' | 'email') => send<{ message: string }>(
      `/settings/email/${kind === 'connection' ? 'test-connection' : 'send-test'}`,
      kind === 'email' ? { recipient } : undefined),
    onMutate: () => setResult(''),
    onSuccess: data => setResult(data.message),
    onError: error => setResult(error.message),
  })
  const busy = save.isPending || test.isPending
  const testDisabled = busy || dirty || !initial.saved
  function edit<K extends keyof Configuration>(key: K, value: Configuration[K]) {
    setForm(previous => ({ ...previous, [key]: value })); setResult('')
  }
  return <div className="mt-5 space-y-5">
    <form onSubmit={event => { event.preventDefault(); save.mutate() }}>
      <fieldset disabled={busy} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-2 text-xs font-medium">SMTP host<Input required maxLength={253} value={form.host} onChange={e => edit('host', e.target.value)} placeholder="smtp.example.com" /></label>
          <label className="space-y-2 text-xs font-medium">SMTP port<Input required type="number" min={1} max={65535} value={form.port || ''} onChange={e => edit('port', Number(e.target.value))} /></label>
          <label className="space-y-2 text-xs font-medium">Security mode<select aria-label="Security mode" className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={form.security} onChange={e => edit('security', e.target.value as Configuration['security'])}>
            <option value="starttls">STARTTLS (usually port 587)</option><option value="tls">TLS (usually port 465)</option><option value="none">None — unauthenticated relay only</option>
          </select></label>
          <label className="space-y-2 text-xs font-medium">Sender name<Input required maxLength={150} value={form.sender_name} onChange={e => edit('sender_name', e.target.value)} /></label>
          <label className="space-y-2 text-xs font-medium">Sender email<Input required type="email" maxLength={254} value={form.sender_email} onChange={e => edit('sender_email', e.target.value)} /></label>
          <label className="space-y-2 text-xs font-medium">SMTP username<Input autoComplete="off" maxLength={320} value={form.username} onChange={e => edit('username', e.target.value)} /></label>
          <label className="space-y-2 text-xs font-medium">SMTP password<Input type="password" autoComplete="new-password" maxLength={1024} value={password} disabled={clearPassword} onChange={e => { setPassword(e.target.value); setResult('') }} aria-describedby="smtp-password-help" /></label>
        </div>
        <p id="smtp-password-help" className="text-xs text-muted-foreground">{initial.password_configured ? 'A password is configured. Leave this field blank to keep it.' : 'No password is configured.'} Enter a new password when changing the username. Leave both credentials empty for an unauthenticated relay.</p>
        {initial.password_configured && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={clearPassword} onChange={e => { setClearPassword(e.target.checked); setPassword(''); setResult('') }} />Clear saved password (also clear the username)</label>}
        {form.security === 'none' && <p className="text-xs text-amber-700">This mode sends email without encryption and does not allow SMTP authentication.</p>}
        <div className="space-y-4 border-t pt-4">
          <h3 className="text-sm font-semibold">Campaign delivery and incoming replies</h3>
          <p className="text-xs text-muted-foreground">Use the mailbox receiving replies for the company sender. Incoming connections use verified TLS. Leave the incoming host empty to disable synchronization; automatic follow-ups will be held.</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-xs font-medium">Maximum campaign messages per hour<Input type="number" required min={1} max={1000} value={form.hourly_limit} onChange={e => edit('hourly_limit', Number(e.target.value))} /></label>
            <label className="space-y-2 text-xs font-medium">Incoming IMAP host<Input maxLength={253} value={form.imap_host} onChange={e => edit('imap_host', e.target.value)} placeholder="imap.example.com" /></label>
            <label className="space-y-2 text-xs font-medium">Incoming TLS port<Input required type="number" min={1} max={65535} value={form.imap_port} onChange={e => edit('imap_port', Number(e.target.value))} /></label>
            <label className="space-y-2 text-xs font-medium">Incoming username<Input autoComplete="off" required={!!form.imap_host} value={form.imap_username} onChange={e => edit('imap_username', e.target.value)} /></label>
            <label className="space-y-2 text-xs font-medium">Incoming password<Input type="password" autoComplete="new-password" value={imapPassword} onChange={e => setImapPassword(e.target.value)} /></label>
          </div>
          <p className="text-xs text-muted-foreground">{initial.imap_password_configured ? 'Incoming password is configured. Leave blank to retain it.' : 'No incoming password is configured.'} Use provider-approved mailbox credentials.</p>
        </div>
        <Button type="submit" disabled={busy}>{save.isPending ? 'Saving…' : 'Save Configuration'}</Button>
      </fieldset>
    </form>
    <div className="space-y-4 border-t pt-5">
      <p className="text-xs text-muted-foreground">Tests use the saved configuration. Save any edits first. Sending a test submits one email to the address below.</p>
      <Button type="button" variant="outline" disabled={testDisabled} onClick={() => test.mutate('connection')}>Test Connection</Button>
      <form className="flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); test.mutate('email') }}>
        <label className="min-w-0 flex-1 space-y-2 text-xs font-medium">Test recipient<Input type="email" required maxLength={254} value={recipient} disabled={busy} onChange={e => setRecipient(e.target.value)} placeholder="you@example.com" /></label>
        <Button type="submit" variant="outline" disabled={testDisabled || !recipient}>Send Test Email</Button>
      </form>
      <p role="status" aria-live="polite" className="text-xs leading-6">{test.isPending ? 'Testing the saved SMTP configuration…' : result}</p>
    </div>
  </div>
}

export function EmailConfigurationSection() {
  const configuration = useQuery({ queryKey, queryFn: () => api<Configuration>('/settings/email'), refetchOnWindowFocus: false })
  return <section className="panel p-6"><h2 className="text-sm font-semibold">Email Configuration</h2>
    <p className="mt-2 text-xs text-muted-foreground">Configure the company sender. Saved changes apply immediately. Only the CEO can manage these settings.</p>
    {configuration.isPending ? <Loading /> : configuration.error ? <ErrorState error={configuration.error} retry={() => { void configuration.refetch() }} /> : <ConfigurationForm key={configuration.data.updated_at ?? 'defaults'} initial={configuration.data} />}
  </section>
}
