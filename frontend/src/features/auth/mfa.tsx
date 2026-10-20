import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import { Download, Fingerprint, LoaderCircle } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Brand } from '@/components/shared'
import { useAuth } from './auth-context'
import { send } from '@/lib/api'
import type { User } from '@/types'

export function MfaGate() {
  const auth = useAuth()
  const [enrollment, setEnrollment] = useState<{ secret: string; uri: string } | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const enrolling = auth.user?.session_state === 'enrollment_required'
  const begin = useMutation({ mutationFn: () => send<{ secret: string; uri: string }>('/auth/mfa/enroll'), onSuccess: setEnrollment })
  const verify = useMutation({ mutationFn: async () => {
    if (enrolling) {
      const result = await send<{ user: User; recovery_codes: string[] }>('/auth/mfa/confirm', { code })
      auth.setRecoveryCodes(result.recovery_codes); auth.setUser(result.user)
    } else auth.setUser(await send<User>('/auth/mfa/verify', { code }))
  }, onError: error => setError(error.message) })
  function download() { const url = URL.createObjectURL(new Blob(['NTECH EMS recovery codes — store privately. Each code can be used once.\n\n' + auth.recoveryCodes.join('\n')], { type: 'text/plain' })); const a = document.createElement('a'); a.href = url; a.download = 'ntech-recovery-codes.txt'; a.click(); URL.revokeObjectURL(url) }
  return <main className="flex min-h-dvh items-center justify-center px-5 py-12"><div className="panel w-full max-w-lg p-7 sm:p-10"><Brand /><div className="mt-9 mb-5 flex size-12 items-center justify-center rounded-xl bg-blue-50 text-primary"><Fingerprint className="size-6" /></div>
    {auth.recoveryCodes.length ? <><h1 className="text-2xl font-semibold tracking-tight">Save your recovery codes</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">These codes are shown once. Store them privately so you can sign in if you lose access to your authenticator.</p><div className="my-5 grid gap-2 rounded-xl border bg-slate-50 p-4 font-mono text-[12px] sm:grid-cols-2">{auth.recoveryCodes.map(code => <span key={code}>{code}</span>)}</div><Button variant="outline" onClick={download} className="mb-4 w-full"><Download className="size-4" />Download recovery codes</Button><Button className="w-full" onClick={() => { setEnrollment(null); auth.setRecoveryCodes([]) }}>I’ve saved my codes · Continue</Button></> : <>
    <h1 className="text-2xl font-semibold tracking-tight">{enrolling ? 'Secure your account' : 'Verify it’s you'}</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">{enrolling ? 'Connect an authenticator app such as Microsoft Authenticator, Google Authenticator, or Aegis.' : 'Enter the current code from your authenticator, or use one of your recovery codes.'}</p>
    {enrolling && !enrollment ? <Button className="mt-6 w-full" disabled={begin.isPending} onClick={() => begin.mutate()}>{begin.isPending && <LoaderCircle className="size-4 animate-spin" />}Set up authenticator</Button> : null}
    {begin.error && <p role="alert" className="mt-3 text-sm text-destructive">{begin.error.message}</p>}
    {enrollment && <div className="my-6 flex flex-col items-center rounded-xl border bg-slate-50 p-5"><QRCodeSVG value={enrollment.uri} size={164} marginSize={2} title="Scan to enroll your NTECH EMS authenticator" /><p className="mt-4 text-xs text-muted-foreground">Or enter this key manually</p><code className="mt-2 max-w-full text-center text-xs break-all select-all">{enrollment.secret}</code></div>}
    {(!enrolling || enrollment) && <form className="mt-6 space-y-4" onSubmit={event => { event.preventDefault(); setError(''); verify.mutate() }}><div><label className="field-label" htmlFor="mfa-code">Authentication or recovery code</label><Input id="mfa-code" autoComplete="one-time-code" value={code} onChange={event => setCode(event.target.value)} required minLength={6} maxLength={40} autoFocus /></div>{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<Button disabled={verify.isPending} className="w-full">{verify.isPending && <LoaderCircle className="size-4 animate-spin" />}Verify and continue</Button></form>}
    <Button variant="ghost" className="mt-5 w-full text-muted-foreground" onClick={() => auth.logout().catch(error => toast.error(error.message))}>Sign out</Button></>}
  </div></main>
}

export function ChangePassword({ required = false }: { required?: boolean }) {
  const auth = useAuth()
  const [error, setError] = useState('')
  const mutation = useMutation({ mutationFn: (data: { current_password: string; new_password: string }) => send<User>('/auth/password', data), onSuccess: user => { auth.setUser(user); toast.success('Password changed. Other sessions have been revoked.') }, onError: error => setError(error.message) })
  return <section className="panel p-6"><h2 className="font-semibold">{required ? 'Choose your own password' : 'Change password'}</h2><p className="mt-2 text-sm text-muted-foreground">{required ? 'Replace your temporary password before entering the workspace.' : 'Use at least 12 characters. Changing your password signs out your other sessions.'}</p><form className="mt-5 max-w-md space-y-4" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); if (form.get('new') !== form.get('confirm')) { setError('New passwords do not match'); return } setError(''); mutation.mutate({ current_password: String(form.get('current')), new_password: String(form.get('new')) }) }}><div><label className="field-label" htmlFor="current-password">Current password</label><Input id="current-password" name="current" type="password" autoComplete="current-password" required /></div><div><label className="field-label" htmlFor="new-password">New password</label><Input id="new-password" name="new" type="password" autoComplete="new-password" required minLength={12} maxLength={128} /></div><div><label className="field-label" htmlFor="confirm-password">Confirm new password</label><Input id="confirm-password" name="confirm" type="password" autoComplete="new-password" required minLength={12} maxLength={128} /></div>{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<Button disabled={mutation.isPending}>Save new password</Button></form></section>
}
