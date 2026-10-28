import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Mail } from 'lucide-react'
import { api, send } from '@/lib/api'
import { useAuth } from '@/features/auth/auth-context'
import { PageHeader, Loading, ErrorState, EmptyState } from '@/components/shared'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

type Content = { subject: string; body: string }
type Step = Content & { days: number }
type Template = Content & { id: string; name: string; category: string; status: string; creator_id: string }
type Message = Content & { id: string; status?: string; due_at?: string; created_at: string; accepted_at?: string; error?: string; step?: number }
type Recipient = { id: string; contact_id: string; email: string; organization: string; organization_id: string; outcome: string; stopped: boolean; variables: Record<string, string>; outgoing: Message[]; incoming: Message[] }
type Campaign = Content & { id: string; name: string; objective: string; description: string; owner: string; owner_id: string; status: string; version: number; steps: Step[]; recipient_count: number; sent: number; replies: number; queued: number; failed: number; pending_followups: number; recipients: Recipient[]; issue?: string; approvals: { id: string; decision: string; note: string; created_at: string }[] }
type Contact = { id: string; full_name: string; job_title: string; email: string; recommended: boolean }
type Org = { id: string; name: string; contacts: Contact[] }
type Preview = Content & { missing: string[] }
const variables = ['contact_name', 'contact_position', 'company_name', 'industry', 'country', 'sender_name', 'sender_title', 'company_website']
const selectClass = 'h-10 w-full rounded-md border bg-background px-3 text-sm'
const date = (value?: string) => value ? new Date(value).toLocaleString() : '—'
const label = (value: string) => value.replaceAll('_', ' ')

function useOperations() { return useAuth().user?.roles.some(r => r === 'CEO' || r === 'Manager') ?? false }

function ProcessingStatus() {
  const query = useQuery({ queryKey: ['campaign-runtime'], queryFn: () => api<{ running: boolean; phase: string; last_completed: string | null; error: string | null; mailbox_last_success: string | null; mailbox_error: string | null }>('/campaigns/runtime'), refetchInterval: 5000 })
  if (query.error) return <ErrorState error={query.error} />
  if (!query.data) return <p className="mb-4 text-xs text-muted-foreground">Checking email processing…</p>
  const state = query.data
  return <div role="status" className={`mb-5 rounded-lg border p-4 text-sm ${!state.running || state.error ? 'border-amber-300 bg-amber-50' : 'bg-white'}`}>
    <p className="font-medium">{state.running ? 'Email processing is running' : 'Email processing is not running — queued messages are waiting'}</p>
    <p className="mt-1 text-xs text-muted-foreground">{state.running ? `Current activity: ${label(state.phase)}. ` : 'Restart the application to restore automatic delivery. '}Last completed cycle: {date(state.last_completed ?? undefined)}.</p>
    {state.error && <p className="mt-2 text-red-700">{state.error}</p>}
    <p className="mt-2 text-xs">Replies last checked: {date(state.mailbox_last_success ?? undefined)}. {state.mailbox_error || (!state.mailbox_last_success ? 'Waiting for the first mailbox check.' : 'Replies automatically stop pending follow-ups.')}</p>
  </div>
}

function ContentEditor({ value, onChange }: { value: Content; onChange: (next: Content) => void }) {
  const [target, setTarget] = useState<'subject' | 'body'>('body')
  return <div className="space-y-3">
    <div className="flex flex-wrap gap-2"><label className="text-xs">Insert into<select aria-label="Variable destination" className={selectClass} value={target} onChange={e => setTarget(e.target.value as 'subject' | 'body')}><option value="body">Body</option><option value="subject">Subject</option></select></label>
      <label className="text-xs">Insert variable<select className={selectClass} value="" onChange={e => { if (e.target.value) onChange({ ...value, [target]: value[target] + '{{' + e.target.value + '}}' }) }}><option value="">Choose variable</option>{variables.map(v => <option key={v} value={v}>{label(v)}</option>)}</select></label></div>
    <label className="block space-y-2 text-sm">Subject<Input required maxLength={500} value={value.subject} onChange={e => onChange({ ...value, subject: e.target.value })} /></label>
    <label className="block space-y-2 text-sm">Plain-text message<Textarea required maxLength={50000} rows={7} value={value.body} onChange={e => onChange({ ...value, body: e.target.value })} /></label>
  </div>
}

export default function Campaigns() {
  const [search, setSearch] = useState('')
  const query = useQuery({ queryKey: ['campaigns', search], queryFn: () => api<{ items: Campaign[]; metrics: { active: number; sent: number; replies: number; pending: number }; mailbox: { last_success: string; error: string } | null }>(`/campaigns?q=${encodeURIComponent(search)}`), refetchInterval: 5000 })
  return <><PageHeader eyebrow="Relationships & outreach" title="Email campaigns" description="Personalized outreach, reviewed before sending." action={<div className="flex flex-wrap gap-2"><Button asChild variant="outline"><Link to="/campaigns/templates">Templates</Link></Button><Button asChild><Link to="/campaigns/new">Create campaign</Link></Button></div>} />
    {query.isPending ? <Loading /> : query.error ? <ErrorState error={query.error} /> : <>
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">{[['Active campaigns', query.data.metrics.active], ['Emails sent', query.data.metrics.sent], ['Replies received', query.data.metrics.replies], ['Pending follow-ups', query.data.metrics.pending]].map(([name, count]) => <section key={name} className="panel p-5"><p className="text-xs text-muted-foreground">{name}</p><p className="mt-3 text-3xl font-semibold">{count}</p></section>)}</div>
      <p className="mb-4 text-xs text-muted-foreground">Sent counts indicate SMTP acceptance, not confirmed delivery. Mailbox last synchronized: {date(query.data.mailbox?.last_success)}. {query.data.mailbox?.error}</p>
      <ProcessingStatus /><section className="panel overflow-hidden"><div className="p-4"><Input aria-label="Search campaigns" placeholder="Search campaigns" value={search} onChange={e => setSearch(e.target.value)} /></div>
        {!query.data.items.length ? <EmptyState icon={Mail} title="No campaigns found" description="Create a campaign using your existing organization contacts." /> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-muted/40 text-xs text-muted-foreground"><tr>{['Campaign', 'Objective', 'Owner', 'Recipients', 'Status', 'Sent / replies', 'Actions'].map(h => <th key={h} className="px-4 py-3">{h}</th>)}</tr></thead><tbody>{query.data.items.map(c => <tr key={c.id} className="border-t"><td className="px-4 py-4 font-medium">{c.name}</td><td className="px-4">{c.objective}</td><td className="px-4">{c.owner}</td><td className="px-4">{c.recipient_count}</td><td className="px-4 capitalize">{label(c.status)}</td><td className="px-4">{c.sent} / {c.replies}<span className="block text-xs text-muted-foreground">{c.queued} queued ? {c.failed} failed / uncertain</span></td><td className="px-4"><div className="flex flex-wrap gap-2 py-2"><Button asChild size="sm" variant="outline"><Link to={`/campaigns/${c.id}`}>View</Link></Button><CampaignActions campaign={c} compact /></div></td></tr>)}</tbody></table></div>}
      </section></>}
    <SuppressionManager />
  </>
}

function CampaignActions({ campaign: c, compact = false }: { campaign: Campaign; compact?: boolean }) {
  const manager = useOperations(), auth = useAuth(), client = useQueryClient()
  const owns = c.owner_id === auth.user?.id
  const [note, setNote] = useState('')
  const mutation = useMutation({ mutationFn: (action: string) => send(`/campaigns/${c.id}/actions`, { action, version: c.version, note }), onSuccess: () => { toast.success('Campaign updated'); void client.invalidateQueries({ queryKey: ['campaigns'] }); void client.invalidateQueries({ queryKey: ['campaign', c.id] }) }, onError: e => toast.error(e.message) })
  const actions: [string, string][] = []
  if (!compact && (manager || owns) && ['draft', 'rejected'].includes(c.status)) actions.push(['review', 'Review'], ['submit', 'Submit for approval'])
  if (!compact && manager && c.status === 'pending_approval') actions.push(['approve', 'Approve'], ['reject', 'Reject'])
  if (!compact && (manager || (owns && auth.can('campaigns.launch'))) && c.status === 'approved') actions.push(['launch', 'Launch campaign'])
  if (manager && c.status === 'active') actions.push(['pause', 'Pause'])
  if (manager && c.status === 'paused') actions.push(['resume', 'Resume'])
  if (manager && !['completed', 'cancelled'].includes(c.status)) actions.push(['cancel', 'Cancel'])
  const editable = ((manager || owns) && ['draft', 'rejected'].includes(c.status)) || (manager && ['approved', 'pending_approval'].includes(c.status))
  return <div className="flex flex-wrap items-center gap-2">{editable && <Button asChild size="sm" variant="outline"><Link to={`/campaigns/${c.id}/edit`}>{c.status === 'draft' ? 'Edit draft' : 'Edit & reset approval'}</Link></Button>}
    {!compact && manager && c.status === 'pending_approval' && <Input aria-label="Approval decision note" placeholder="Decision note (optional)" value={note} maxLength={2000} onChange={e => setNote(e.target.value)} />}
    {actions.map(([action, text]) => <Button key={action} size="sm" variant="outline" disabled={mutation.isPending} onClick={() => mutation.mutate(action)}>{text}</Button>)}</div>
}

export function CampaignDetail() {
  const { id } = useParams(), client = useQueryClient()
  const manager = useOperations(), auth = useAuth()
  const [search, setSearch] = useState('')
  const query = useQuery({ queryKey: ['campaign', id], queryFn: () => api<Campaign>(`/campaigns/${id}`), refetchInterval: 5000 })
  const outcome = useMutation({ mutationFn: ({ recipient, value }: { recipient: string; value: string }) => send(`/campaigns/${id}/recipients/${recipient}/outcome`, { outcome: value }), onSuccess: () => { void client.invalidateQueries({ queryKey: ['campaign', id] }); toast.success('Follow-ups stopped and outcome saved') }, onError: e => toast.error(e.message) })
  if (query.isPending) return <Loading />
  if (query.error) return <ErrorState error={query.error} />
  const c = query.data
  const canManage = manager || c.owner_id === auth.user?.id
  return <><Button asChild variant="ghost"><Link to="/campaigns">Back to campaigns</Link></Button><PageHeader title={c.name} description={`${c.objective} · ${c.owner} · ${label(c.status)}`} action={<CampaignActions campaign={c} />} />
    <ProcessingStatus />
    {c.status === 'paused' && <p className="mb-4 rounded-lg border bg-amber-50 p-4 text-sm">This campaign is paused. No queued initial emails or follow-ups will be sent. Replies are still checked and stop follow-ups. Resume keeps the original schedule, so overdue messages become eligible immediately.</p>}
    <p className="mb-4 text-sm">{c.queued} messages queued · {c.failed} failed or uncertain</p>
    {!canManage && <p className="mb-4 text-sm text-muted-foreground">You have read-only access to this campaign.</p>}
    {c.issue && <p role="alert" className="mb-4 rounded border border-amber-300 p-4 text-sm">{c.issue}</p>}
    <section className="panel mb-5 space-y-3 p-5"><p>{c.description}</p><p className="text-sm">{c.recipient_count} recipients · {c.sent} accepted messages · {c.replies} replies · {c.pending_followups} pending follow-ups</p><h2 className="font-semibold">{c.subject}</h2><p className="whitespace-pre-wrap text-sm">{c.body}</p>{c.steps.map((s, i) => <p key={i} className="text-xs">Follow-up {i + 1}: {s.days} days after the preceding accepted message — {s.subject}</p>)}
      {c.approvals.map(a => <p key={a.id} className="text-xs text-muted-foreground">{date(a.created_at)} · {a.decision} · {a.note}</p>)}</section>
    <Input className="mb-4" aria-label="Search conversations" placeholder="Search by email, organization or outcome" value={search} onChange={e => setSearch(e.target.value)} />
    <div className="space-y-4">{c.recipients.filter(r => `${r.email} ${r.organization} ${r.outcome}`.toLowerCase().includes(search.toLowerCase())).map(r => <details key={r.id} className="panel p-5"><summary className="cursor-pointer break-words font-medium">{r.variables.contact_name} · {r.email} <span className="text-xs font-normal">— {label(r.outcome)}{r.stopped ? ' · Follow-ups stopped' : ''}</span></summary>
      <div className="mt-4 space-y-4"><Link className="text-sm text-primary underline" to={`/organizations/${r.organization_id}`}>{r.organization}</Link>
        {canManage && <label className="block max-w-sm text-sm">Record response and stop follow-ups<select aria-label={`Outcome for ${r.email}`} className={selectClass} value="" disabled={outcome.isPending} onChange={e => { if (e.target.value) outcome.mutate({ recipient: r.id, value: e.target.value }) }}><option value="">Choose outcome</option>{['replied', 'interested', 'not_interested', 'do_not_follow_up', 'requires_attention', 'do_not_contact'].map(v => <option key={v} value={v}>{label(v)}</option>)}</select></label>}
        {!r.outgoing.length && <p className="text-sm text-muted-foreground">No messages scheduled yet. Launch after approval.</p>}
        {[...r.outgoing.map(m => ({ ...m, direction: 'Outgoing', timestamp: m.accepted_at || m.due_at || m.created_at })), ...r.incoming.map(m => ({ ...m, direction: 'Reply', timestamp: m.created_at }))].sort((a, b) => a.timestamp.localeCompare(b.timestamp)).map(m => <article key={m.id} className="rounded-lg border p-4"><p className="text-xs text-muted-foreground">{m.direction} · {m.status || 'received'} · {date(m.timestamp)}</p><h3 className="mt-2 font-medium">{m.subject}</h3><p className="mt-2 whitespace-pre-wrap break-words text-sm">{m.body}</p>{m.error && <p className="mt-2 text-sm text-red-700">{m.error}</p>}</article>)}
      </div></details>)}</div></>
}

export function CampaignEditor() {
  const { id } = useParams()
  const manager = useOperations(), auth = useAuth()
  const query = useQuery({ queryKey: ['campaign', id], queryFn: () => api<Campaign>(`/campaigns/${id}`), enabled: !!id })
  if (id && query.isPending) return <Loading />
  if (query.error) return <ErrorState error={query.error} />
  if (query.data && !manager && query.data.owner_id !== auth.user?.id) return <section className="panel space-y-3 p-5"><p>You have read-only access to this campaign.</p><Link className="text-primary underline" to={`/campaigns/${id}`}>View campaign</Link></section>
  return <CampaignForm key={id || 'new'} initial={query.data} />
}

function CampaignForm({ initial }: { initial?: Campaign }) {
  const navigate = useNavigate(), client = useQueryClient()
  const [form, setForm] = useState({ name: initial?.name || '', objective: initial?.objective || 'Partnership', description: initial?.description || '', subject: initial?.subject || '', body: initial?.body || '', steps: initial?.steps || [] as Step[], contact_ids: initial?.recipients.map(r => r.contact_id).filter(Boolean) || [] as string[] })
  const [search, setSearch] = useState(''), [previewContact, setPreviewContact] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [selectedOrgs, setSelectedOrgs] = useState<Org[]>([])
  const templates = useQuery({ queryKey: ['templates'], queryFn: () => api<Template[]>('/campaigns/templates') })
  const orgs = useQuery({ queryKey: ['campaign-contacts', search], queryFn: () => api<Org[]>(`/campaigns/contacts?q=${encodeURIComponent(search)}`) })
  const available = [...selectedOrgs, ...(orgs.data || []).filter(o => !selectedOrgs.some(s => s.id === o.id))]
  const selectedContacts = available.flatMap(o => o.contacts).filter(c => form.contact_ids.includes(c.id))
  const previewOptions = [...selectedContacts.map(c => ({ id: c.id, name: c.full_name })), ...(initial?.recipients || []).filter(r => form.contact_ids.includes(r.contact_id) && !selectedContacts.some(c => c.id === r.contact_id)).map(r => ({ id: r.contact_id, name: r.email }))]
  const save = useMutation({ mutationFn: async (action: string) => {
    const c = await send<Campaign>(initial ? `/campaigns/${initial.id}` : '/campaigns', { ...form, version: initial?.version }, initial ? 'PUT' : 'POST')
    // Complete the transition before mounting detail, avoiding a concurrent draft fetch.
    try {
      if (action !== 'save') await send(`/campaigns/${c.id}/actions`, { action, version: c.version })
    } finally {
      await client.invalidateQueries({ queryKey: ['campaign', c.id] })
      navigate(`/campaigns/${c.id}`)
    }
    return c
  }, onSuccess: () => { void client.invalidateQueries({ queryKey: ['campaigns'] }); void client.invalidateQueries({ queryKey: ['campaign'] }); toast.success('Campaign saved') }, onError: e => toast.error(e.message) })
  const previewMutation = useMutation({ mutationFn: () => send<Preview>('/campaigns/preview', { subject: form.subject, body: form.body, contact_id: previewContact }), onSuccess: setPreview, onError: e => toast.error(e.message) })
  function chooseOrg(org: Org) {
    if (selectedOrgs.some(o => o.id === org.id)) {
      setSelectedOrgs(selectedOrgs.filter(o => o.id !== org.id)); setForm({ ...form, contact_ids: form.contact_ids.filter(id => !org.contacts.some(c => c.id === id)) })
    } else {
      setSelectedOrgs([...selectedOrgs, org]); const first = org.contacts.find(c => c.recommended) || org.contacts[0]
      if (first) setForm({ ...form, contact_ids: [...new Set([...form.contact_ids, first.id])] })
    }
  }
  return <><PageHeader title={initial ? 'Edit campaign' : 'Create campaign'} description="Choose recipients deliberately, personalize your message, and submit it for approval." /><form onSubmit={e => { e.preventDefault(); save.mutate('save') }} className="space-y-5"><fieldset disabled={save.isPending} className="space-y-5">
    <section className="panel space-y-4 p-5"><h2 className="font-semibold">1. Campaign details</h2><label className="block text-sm">Campaign name<Input required maxLength={150} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label><label className="block text-sm">Objective<select className={selectClass} value={form.objective} onChange={e => setForm({ ...form, objective: e.target.value })}>{['Partnership', 'Customer Acquisition', 'General Outreach'].map(v => <option key={v}>{v}</option>)}</select></label><label className="block text-sm">Description<Textarea maxLength={5000} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></label></section>
    <section className="panel space-y-4 p-5"><h2 className="font-semibold">2. Recipients ({form.contact_ids.length} selected)</h2><p className="text-xs text-muted-foreground">Selecting an organization chooses one recommended contact. Select additional contacts only when appropriate.</p><Input aria-label="Search organizations" placeholder="Search existing organizations" value={search} onChange={e => setSearch(e.target.value)} />
      {orgs.error && <ErrorState error={orgs.error} />}{orgs.isPending && <p className="text-sm">Loading contacts…</p>}
      {initial && <div className="flex flex-wrap gap-2">{initial.recipients.filter(r => form.contact_ids.includes(r.contact_id)).map(r => <Button key={r.id} type="button" variant="outline" size="sm" onClick={() => setForm({ ...form, contact_ids: form.contact_ids.filter(id => id !== r.contact_id) })}>Remove {r.email}</Button>)}</div>}
      <div className="max-h-96 space-y-4 overflow-y-auto">{available.map(org => <div key={org.id} className="rounded-lg border p-3"><label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={selectedOrgs.some(o => o.id === org.id)} onChange={() => chooseOrg(org)} />{org.name}</label>{!org.contacts.length ? <p className="mt-2 text-xs">No contacts with email. <Link className="text-primary underline" to={`/organizations/${org.id}`}>Manage contacts</Link></p> : <div className="mt-3 space-y-2">{org.contacts.map(c => <label key={c.id} className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={form.contact_ids.includes(c.id)} onChange={e => { setSelectedOrgs(prev => prev.some(o => o.id === org.id) ? prev : [...prev, org]); setForm({ ...form, contact_ids: e.target.checked ? [...new Set([...form.contact_ids, c.id])] : form.contact_ids.filter(id => id !== c.id) }) }} /><span className="min-w-0 break-words">{c.full_name} · {c.job_title || 'Position not provided'}<span className="block text-xs text-muted-foreground">{c.email}{c.recommended ? ' · Recommended' : ''}</span></span></label>)}</div>}</div>)}{!orgs.isPending && !available.length && <p className="text-sm">No organizations found. <Link to="/organizations" className="text-primary underline">Manage organizations</Link></p>}</div></section>
    <section className="panel space-y-4 p-5"><h2 className="font-semibold">3. Email content</h2>{templates.error && <ErrorState error={templates.error} />}<label className="block text-sm">Use template<select className={selectClass} defaultValue="" onChange={e => { const t = templates.data?.find(t => t.id === e.target.value); if (t) setForm({ ...form, subject: t.subject, body: t.body }) }}><option value="">Choose a template (optional)</option>{templates.data?.filter(t => t.status === 'active').map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label><ContentEditor value={form} onChange={v => { setForm({ ...form, ...v }); setPreview(null) }} />
      <div className="flex flex-wrap gap-3"><select aria-label="Preview recipient" className={selectClass} value={previewContact} onChange={e => { setPreviewContact(e.target.value); setPreview(null) }}><option value="">Select recipient for preview</option>{previewOptions.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select><Button type="button" variant="outline" disabled={!previewContact || previewMutation.isPending || !form.subject || !form.body} onClick={() => previewMutation.mutate()}>Preview message</Button></div>{preview && <article className="rounded-lg border bg-muted/30 p-4"><h3 className="font-medium">{preview.subject}</h3><p className="mt-2 whitespace-pre-wrap text-sm">{preview.body}</p>{preview.missing.length > 0 && <p role="alert" className="mt-3 text-sm text-red-700">Missing: {preview.missing.join(', ')}. Sending will be blocked.</p>}</article>}</section>
    <section className="panel space-y-4 p-5"><h2 className="font-semibold">4. Automatic follow-ups</h2><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.steps.length > 0} onChange={e => setForm({ ...form, steps: e.target.checked ? [{ days: 4, subject: '', body: '' }] : [] })} />Enable follow-ups when no response is received</label>
      {form.steps.map((step, i) => <div key={i} className="space-y-3 rounded-lg border p-4"><h3 className="font-medium">Follow-up {i + 1}</h3><label className="block text-sm">Days after the previous accepted message<Input required type="number" min={1} max={365} value={step.days} onChange={e => setForm({ ...form, steps: form.steps.map((s, n) => n === i ? { ...s, days: Number(e.target.value) } : s) })} /></label><ContentEditor value={step} onChange={v => setForm({ ...form, steps: form.steps.map((s, n) => n === i ? { ...s, ...v } : s) })} /><Button type="button" variant="ghost" onClick={() => setForm({ ...form, steps: form.steps.filter((_, n) => n !== i) })}>Remove follow-up</Button></div>)}
      {form.steps.length > 0 && form.steps.length < 3 && <Button type="button" variant="outline" onClick={() => setForm({ ...form, steps: [...form.steps, { days: 7, subject: '', body: '' }] })}>Add follow-up</Button>}
      <p className="text-xs text-muted-foreground">{form.steps.length ? `Initial message → ${form.steps.map((s, i) => `Follow-up ${i + 1} after ${s.days} days`).join(' → ')}. Replies stop the sequence. Healthy incoming-mail synchronization is required.` : 'Only the initial message will be sent.'}</p></section>
    <div className="flex flex-wrap gap-3"><Button type="submit" disabled={!form.contact_ids.length}>Save draft</Button><Button type="button" variant="outline" disabled={!form.contact_ids.length} onClick={() => save.mutate('review')}>Save & review</Button><Button type="button" variant="outline" disabled={!form.contact_ids.length} onClick={() => save.mutate('submit')}>Submit for approval</Button><Button asChild variant="ghost"><Link to="/campaigns">Back</Link></Button></div>
  </fieldset></form></>
}

export function Templates() {
  const client = useQueryClient(), auth = useAuth(), manager = useOperations()
  const [editing, setEditing] = useState<Template | null>(null)
  const blank = { name: '', category: 'General Outreach', subject: '', body: '', status: 'active' }
  const [form, setForm] = useState(blank)
  const query = useQuery({ queryKey: ['templates'], queryFn: () => api<Template[]>('/campaigns/templates') })
  const save = useMutation({ mutationFn: () => send(editing ? `/campaigns/templates/${editing.id}` : '/campaigns/templates', form, editing ? 'PUT' : 'POST'), onSuccess: () => { void client.invalidateQueries({ queryKey: ['templates'] }); setEditing(null); setForm(blank); toast.success('Template saved') }, onError: e => toast.error(e.message) })
  return <><PageHeader title="Email templates" description="Reusable plain-text messages. Campaign edits never change the source template." action={<Button asChild variant="outline"><Link to="/campaigns">Campaigns</Link></Button>} />
    <div className="grid items-start gap-5 xl:grid-cols-2"><section className="panel p-5">{query.isPending ? <Loading /> : query.error ? <ErrorState error={query.error} /> : query.data.length ? query.data.map(t => <article key={t.id} className="space-y-2 border-b py-4"><h2 className="font-medium">{t.name}</h2><p className="text-xs text-muted-foreground">{t.category} · {t.status}</p><details><summary className="cursor-pointer text-sm">Preview content</summary><p className="mt-2 font-medium">{t.subject}</p><p className="whitespace-pre-wrap break-words text-sm">{t.body}</p></details>{(manager || t.creator_id === auth.user?.id) && <Button variant="outline" size="sm" onClick={() => { setEditing(t); setForm({ name: t.name, category: t.category, subject: t.subject, body: t.body, status: t.status }) }}>Edit / archive</Button>}</article>) : <p className="text-sm text-muted-foreground">No templates yet. Create your first reusable message.</p>}</section>
      <form className="panel space-y-4 p-5" onSubmit={e => { e.preventDefault(); save.mutate() }}><h2 className="font-semibold">{editing ? 'Edit template' : 'Create template'}</h2><label className="block text-sm">Name<Input required maxLength={150} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label><label className="block text-sm">Category<Input required maxLength={60} value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} /></label><ContentEditor value={form} onChange={v => setForm({ ...form, ...v })} /><label className="block text-sm">Status<select className={selectClass} value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}><option value="active">Active</option><option value="archived">Archived</option></select></label><Button disabled={save.isPending}>Save template</Button>{editing && <Button type="button" variant="ghost" onClick={() => { setEditing(null); setForm(blank) }}>New template</Button>}</form></div></>
}

function SuppressionManager() {
  const manager = useOperations(), client = useQueryClient()
  const [email, setEmail] = useState(''), [reason, setReason] = useState('')
  const query = useQuery({ queryKey: ['suppressions'], queryFn: () => api<{ id: string; email: string; reason: string }[]>('/campaigns/suppressions'), enabled: manager })
  const save = useMutation({ mutationFn: () => send('/campaigns/suppressions', { email, reason }), onSuccess: () => { void client.invalidateQueries({ queryKey: ['suppressions'] }); setEmail(''); setReason(''); toast.success('Address suppressed') }, onError: e => toast.error(e.message) })
  if (!manager) return null
  return <details className="panel mt-5 p-5"><summary className="cursor-pointer font-medium">Do not contact list</summary><form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={e => { e.preventDefault(); save.mutate() }}><label className="text-sm">Email<Input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label><label className="text-sm">Reason<Input required maxLength={300} value={reason} onChange={e => setReason(e.target.value)} /></label><Button disabled={save.isPending}>Suppress address</Button></form>{query.error && <ErrorState error={query.error} />}<ul className="mt-4 space-y-2 text-sm">{query.data?.map(r => <li key={r.id} className="break-words">{r.email} — {r.reason}</li>)}</ul></details>
}
