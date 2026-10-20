import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ArrowRight, Eye, EyeOff, Fingerprint, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Brand, Loading } from '@/components/shared'
import { useAuth } from './auth-context'
import { send } from '@/lib/api'
import type { User } from '@/types'

export default function LoginPage() {
  const auth = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (auth.loading) return <Loading />
  if (auth.user) return <Navigate to="/" replace />
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const form = new FormData(event.currentTarget)
    try { auth.setUser(await send<User>('/auth/login', { email: form.get('email'), password: form.get('password') })) }
    catch (error) { setError((error as Error).message) }
    finally { setBusy(false) }
  }
  return <main className="grid min-h-dvh lg:grid-cols-[.95fr_1.05fr]">
    <section className="relative hidden flex-col justify-between overflow-hidden bg-[#14213a] p-12 text-white lg:flex xl:p-16">
      <Brand dark />
      <div className="relative z-10 my-20 max-w-md"><div className="mb-8 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-slate-300"><span className="size-1.5 rounded-full bg-emerald-300" />Built for ETS-NTECH</div><h1 className="text-[46px] leading-[1.12] font-semibold tracking-[-.045em]">Your relationships.<br />Your operations.<br /><span className="text-[#85d6c7]">One workspace.</span></h1><p className="mt-6 text-sm leading-7 text-slate-300">A connected view of the people, organizations, and partnerships moving your business forward.</p><div className="mt-10 space-y-4 text-sm text-slate-300"><p className="flex items-center gap-3"><ShieldCheck className="size-4 text-emerald-300" />Permission-controlled business information</p><p className="flex items-center gap-3"><Fingerprint className="size-4 text-emerald-300" />Multifactor authentication</p></div></div>
      <p className="text-xs text-slate-400">ETS-NTECH · Enterprise Network Technology</p>
      <div aria-hidden className="absolute -right-44 -bottom-48 size-[520px] rounded-full border border-white/5 shadow-[0_0_0_60px_#ffffff03,0_0_0_120px_#ffffff02]" />
    </section>
    <section className="flex items-center justify-center bg-white px-6 py-12 sm:px-12"><div className="w-full max-w-[380px]"><div className="mb-12 lg:hidden"><Brand /></div><div className="mb-6 flex size-12 items-center justify-center rounded-xl border bg-slate-50"><LockKeyhole className="size-5 text-primary" /></div><p className="mb-2 text-[11px] font-semibold tracking-[.16em] text-muted-foreground uppercase">Your enterprise workspace</p><h2 className="text-3xl font-semibold tracking-tight">Welcome back</h2><p className="mt-3 text-sm text-muted-foreground">Sign in with your ETS-NTECH account to continue.</p>
    <form onSubmit={submit} className="mt-8 space-y-5"><div><label htmlFor="email" className="field-label">Email address</label><Input id="email" name="email" type="email" autoComplete="username" placeholder="you@etsntech.org" required /></div><div><label htmlFor="password" className="field-label">Password</label><div className="relative"><Input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required className="pr-11" /><button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'} className="absolute top-0 right-0 flex size-10 items-center justify-center text-muted-foreground">{showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button></div></div>{error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}<Button className="h-11 w-full" disabled={busy}>{busy ? <LoaderCircle className="size-4 animate-spin" /> : <>Sign in<ArrowRight className="size-4" /></>}</Button></form>
    <p className="mt-7 text-center text-xs leading-6 text-muted-foreground">Need access or help with your account?<br />Contact your workspace administrator.</p><div className="mt-12 flex items-center justify-center gap-2 border-t pt-6 text-[11px] text-muted-foreground"><ShieldCheck className="size-3.5" />Protected workspace · MFA required</div></div></section>
  </main>
}
