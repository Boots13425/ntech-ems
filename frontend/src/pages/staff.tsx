import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, ChevronLeft, ChevronRight, Pencil, Plus, KeyRound, Search, Users } from 'lucide-react'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { EmptyState, ErrorState, Loading, PageHeader } from '@/components/shared'
import { useAuth } from '@/features/auth/auth-context'
import { api, send } from '@/lib/api'
import { initials } from '@/lib/utils'
import type { Page, User } from '@/types'

const responsibilities = ['Business Development', 'Partnership Management', 'Sales and Outreach', 'Project Operations']
type TemporaryCredential = User & { temporary_password: string }
function TemporaryPasswordDialog({ created, reset = false, onClose }: { created: TemporaryCredential; reset?: boolean; onClose: () => void }) {
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const passwordInput = useRef<HTMLInputElement>(null)
  async function copyPassword() {
    try {
      // Copy the visible input inside the modal so its focus trap does not
      // interfere. This also works on LAN HTTP where Clipboard API is absent.
      const input = passwordInput.current
      const previousFocus = document.activeElement
      let didCopy = false
      if (input) {
        input.focus()
        input.select()
        input.setSelectionRange(0, input.value.length)
        try { didCopy = document.execCommand('copy') } catch { /* Try Clipboard API below. */ }
        if (previousFocus instanceof HTMLElement) previousFocus.focus()
      }
      if (!didCopy) {
        if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
        await navigator.clipboard.writeText(created.temporary_password)
      }
      setCopied(true)
      toast.success('Temporary password copied')
    } catch {
      setCopied(false)
      setError('Unable to copy automatically. Select the password and copy it manually.')
    }
  }
  return <Dialog open onOpenChange={open => { if (!open) onClose() }}><DialogContent><DialogHeader><DialogTitle>{reset ? "Staff password reset" : "Staff account created"}</DialogTitle><DialogDescription>Share this temporary password privately with {created.full_name} ({created.email}). They must change it at next sign-in. {created.mfa_enabled ? "Their existing authenticator is still required." : "They must also enroll MFA."}</DialogDescription></DialogHeader><div className="space-y-4"><div><label htmlFor="generated-password" className="field-label">Temporary password</label><div className="flex gap-2"><Input ref={passwordInput} id="generated-password" readOnly value={created.temporary_password} className="font-mono" onFocus={event => event.target.select()} /><Button type="button" variant="outline" size="icon" aria-label="Copy temporary password" onClick={() => { setError(''); void copyPassword() }}>{copied ? <Check className="size-4" /> : <Copy className="size-4" />}</Button></div><p role="status" className="mt-2 text-xs text-muted-foreground">{copied ? 'Password copied.' : 'Copy this password before closing. It cannot be viewed again.'}</p></div>{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<div className="flex justify-end"><Button onClick={onClose}>Done</Button></div></div></DialogContent></Dialog>
}
function StaffForm({ user, onClose }: { user?: User; onClose: () => void }) {
  const client = useQueryClient()
  const [error, setError] = useState('')
  const [created, setCreated] = useState<(User & { temporary_password: string }) | null>(null)
  const mutation = useMutation({ mutationFn: (body: Record<string, unknown>) => send<User & { temporary_password: string }>(user ? `/staff/${user.id}` : '/staff', body, user ? 'PUT' : 'POST'), gcTime: 0, onSuccess: result => { void client.invalidateQueries({ queryKey: ['staff'] }); void client.invalidateQueries({ queryKey: ['staff-owners'] }); void client.invalidateQueries({ queryKey: ['dashboard'] }); toast.success(user ? 'Staff account updated' : 'Staff account created. Share the temporary password securely.'); setError(''); if (user) onClose(); else setCreated(result) }, onError: error => setError(error.message) })
  if (created) return <TemporaryPasswordDialog created={created} onClose={onClose} />
  return <Dialog open onOpenChange={open => { if (!open && !mutation.isPending) onClose() }}><DialogContent className="max-h-[90dvh] overflow-y-auto"><DialogHeader><DialogTitle>{user ? 'Edit staff access' : 'Add a team member'}</DialogTitle><DialogDescription>{user ? 'Manage this account’s role, responsibilities, and activation.' : 'The member must enroll MFA and change their temporary password at first sign-in.'}</DialogDescription></DialogHeader><form className="mt-3 space-y-4" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); mutation.mutate({ full_name: form.get('full_name'), role: form.get('role'), responsibilities: form.getAll('responsibilities'), ...(user ? { is_active: form.get('is_active') === 'on' } : { email: form.get('email') }) }) }}><div><label htmlFor="staff-name" className="field-label">Full name</label><Input id="staff-name" name="full_name" defaultValue={user?.full_name} required minLength={2} maxLength={150} /></div>{!user && <><div><label htmlFor="staff-email" className="field-label">Email address</label><Input id="staff-email" name="email" type="email" autoComplete="off" required /></div><p className="text-xs text-muted-foreground">A temporary password will be generated automatically after you create the account.</p></>}
  <div><label htmlFor="staff-role" className="field-label">Primary role</label><select id="staff-role" name="role" className="select-input" defaultValue={user?.roles[0] || 'Staff'}>{['CEO', 'Manager', 'Staff'].map(role => <option key={role}>{role}</option>)}</select></div><fieldset><legend className="field-label">Functional responsibilities</legend><div className="space-y-3">{responsibilities.map(value => <label key={value} className="flex items-center gap-2 text-xs"><input type="checkbox" name="responsibilities" value={value} defaultChecked={user?.responsibilities.includes(value)} className="size-4 accent-primary" />{value}</label>)}</div></fieldset>{user && <label className="flex items-center gap-2 border-t pt-4 text-xs"><input type="checkbox" name="is_active" defaultChecked={user.is_active} className="size-4 accent-primary" />Account is active</label>}{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<div className="flex justify-end gap-2 border-t pt-4"><Button type="button" variant="outline" disabled={mutation.isPending} onClick={onClose}>Cancel</Button><Button disabled={mutation.isPending}>{user ? 'Save changes' : 'Create account'}</Button></div></form></DialogContent></Dialog>
}
export default function StaffPage() {
  const auth = useAuth()
  const [editor, setEditor] = useState<User | 'new' | null>(null)
  const client = useQueryClient()
  const [resetCredential, setResetCredential] = useState<TemporaryCredential | null>(null)
  const resetPassword = useMutation({
    mutationFn: (user: User) => send<TemporaryCredential>(`/staff/${user.id}/reset-password`),
    gcTime: 0,
    onSuccess: result => { setResetCredential(result); void client.invalidateQueries({ queryKey: ['staff'] }); toast.success('Staff password reset') },
    onError: (error: Error) => toast.error(error.message),
  })
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const query = useQuery({ queryKey: ['staff', q, page], queryFn: () => api<Page<User>>(`/staff?q=${encodeURIComponent(q)}&page=${page}`) })
  return <><PageHeader eyebrow="People & access" title="Staff management" description="Manage the people, roles, and responsibilities behind your business." action={auth.can('staff.manage') ? <Button onClick={() => setEditor('new')}><Plus className="size-4" />Add team member</Button> : undefined} /><section className="panel"><div className="border-b p-4"><form role="search" onSubmit={event => { event.preventDefault(); setPage(1); setQ(search) }} className="flex max-w-sm items-center gap-2"><Input aria-label="Search staff" placeholder="Search team members…" value={search} onChange={event => setSearch(event.target.value)} /><Button size="icon" variant="outline" aria-label="Search staff"><Search className="size-4" /></Button></form></div>{query.isPending ? <Loading /> : query.error ? <div className="p-5"><ErrorState error={query.error} retry={() => { void query.refetch() }} /></div> : !query.data.items.length ? <EmptyState icon={Users} title="No team members found" description="Try another search, or add a staff account to the workspace." /> : <div className="divide-y">{query.data.items.map(user => <div key={user.id} className="flex flex-wrap items-center gap-4 px-5 py-5"><span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-500">{initials(user.full_name)}</span><div className="min-w-0 flex-1 basis-32"><h2 className="truncate text-xs font-semibold">{user.full_name}{user.id === auth.user!.id && <span className="ml-2 font-normal text-muted-foreground">(you)</span>}</h2><p className="mt-1.5 truncate text-[11px] text-muted-foreground">{user.email}</p></div><div className="min-w-24 text-xs"><Badge variant="outline" className="text-[10px]">{user.roles.join(', ')}</Badge><p className="mt-1.5 text-[10px] text-muted-foreground">{user.mfa_enabled ? 'MFA enabled' : 'MFA enrollment pending'}</p></div><div className="hidden w-44 text-[10px] leading-5 text-muted-foreground xl:block">{user.responsibilities.join(' · ') || 'Role permissions only'}</div><span className={`rounded-full px-2 py-1 text-[9px] ${user.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>{user.is_active ? 'Active' : 'Inactive'}</span>{auth.can('staff.manage') && <Button variant="ghost" size="icon" aria-label={`Edit ${user.full_name}`} onClick={() => setEditor(user)}><Pencil className="size-3.5" /></Button>}{auth.can('staff.manage') && auth.user!.roles.includes('CEO') && user.id !== auth.user!.id && <Button variant="outline" size="sm" aria-label={`Reset password for ${user.full_name}`} disabled={resetPassword.isPending || !user.is_active} onClick={() => resetPassword.mutate(user)}><KeyRound className="size-3.5" />{resetPassword.isPending && resetPassword.variables?.id === user.id ? 'Resetting...' : 'Reset password'}</Button>}</div>)}</div>}{query.data && <div className="flex items-center justify-between border-t p-4 text-xs text-muted-foreground"><span>{query.data.total} team members · Page {page}</span><div className="flex gap-2"><Button size="icon" variant="outline" disabled={page === 1} aria-label="Previous page" onClick={() => setPage(page - 1)}><ChevronLeft className="size-4" /></Button><Button size="icon" variant="outline" disabled={page * 20 >= query.data.total} aria-label="Next page" onClick={() => setPage(page + 1)}><ChevronRight className="size-4" /></Button></div></div>}</section>{editor && <StaffForm user={editor === 'new' ? undefined : editor} onClose={() => setEditor(null)} />}{resetCredential && <TemporaryPasswordDialog reset created={resetCredential} onClose={() => { setResetCredential(null); resetPassword.reset() }} />}</>
}
