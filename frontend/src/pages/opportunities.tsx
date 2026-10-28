import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Target } from 'lucide-react'
import { useAuth } from '@/features/auth/auth-context'
import { api, send } from '@/lib/api'
import { PageHeader, Loading, ErrorState, EmptyState } from '@/components/shared'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

const stages = ['new', 'qualified', 'proposal', 'negotiation', 'won', 'lost']
const selectClass = 'select-input w-full'
type Task = { id: string; opportunity_id: string; title: string; notes: string; due_at: string; completed_at: string | null; version: number }
type Opportunity = { id: string; title: string; organization_id: string; organization: string; owner_id: string | null; owner: string | null; stage: string; estimated_value: string | null; currency: string; expected_close: string | null; loss_reason: string; notes: string; version: number; next_action: Task | null }
type Detail = Opportunity & { can_edit: boolean; tasks: Task[]; campaigns: { id: string; name: string; status: string }[]; activity: { id: string; action: string; actor_name: string; created_at: string; details: Record<string, unknown> }[] }
const date = (v: string) => new Date(v).toLocaleString()
const manager = (roles: string[]) => roles.some(r => ['CEO', 'Manager'].includes(r))
function useRefresh() { const client = useQueryClient(); return () => { void client.invalidateQueries({ queryKey: ['opportunities'] }); void client.invalidateQueries({ queryKey: ['notifications'] }); void client.invalidateQueries({ queryKey: ['campaign'] }) } }

export function MyWork() {
  const query = useQuery({ queryKey: ['opportunities', 'work'], queryFn: () => api<{ items: (Task & { opportunity_title: string; overdue: boolean })[] }>('/opportunities/work'), refetchInterval: 30_000 })
  return <section className="panel mb-6 p-5"><h2 className="text-base font-semibold">My work today</h2><p className="mt-1 text-xs text-muted-foreground">Your open follow-ups due today or overdue. Dates use Africa/Douala for the daily cutoff.</p>
    {query.isPending ? <Loading /> : query.error ? <ErrorState error={query.error} /> : !query.data.items.length ? <p className="mt-4 text-sm text-muted-foreground">No follow-ups due. Review your opportunities and schedule the next action.</p> : <ul className="mt-3 divide-y">{query.data.items.map(t => <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-3"><Link to={`/opportunities/${t.opportunity_id}`} className="text-sm font-medium text-primary underline">{t.title}<span className="block text-xs font-normal text-muted-foreground">{t.opportunity_title}</span></Link><span className={`text-xs ${t.overdue ? 'text-red-700' : 'text-muted-foreground'}`}>{t.overdue ? 'Overdue · ' : ''}{date(t.due_at)}</span></li>)}</ul>}
  </section>
}

export default function Opportunities() {
  const [q, setQ] = useState(''), [stage, setStage] = useState(''), [filter, setFilter] = useState('all'), [page, setPage] = useState(1)
  const query = useQuery({ queryKey: ['opportunities', 'list', q, stage, filter, page], queryFn: () => api<{ items: Opportunity[]; total: number; stages: Record<string, number>; pipeline_values: Record<string, string>; by_owner: { owner: string; stage: string; count: number }[] }>(`/opportunities?q=${encodeURIComponent(q)}&filter=${filter}&page=${page}${stage ? `&stage=${stage}` : ''}`) })
  return <><PageHeader title="Opportunities" eyebrow="Business development" description="Turn customer interest into assigned work and measurable outcomes." action={<Button asChild><Link to="/opportunities/new"><Plus className="size-4" />New opportunity</Link></Button>} />
    <MyWork />
    {query.data && <><div className="mb-5 grid grid-cols-3 gap-3 lg:grid-cols-6">{stages.map(s => <button key={s} className={`panel p-4 text-left ${stage === s ? 'ring-2 ring-primary' : ''}`} onClick={() => { setStage(stage === s ? '' : s); setPage(1) }}><span className="text-xs capitalize">{s}</span><strong className="mt-2 block text-2xl">{query.data.stages[s] || 0}</strong></button>)}</div><p className="mb-4 text-xs text-muted-foreground">Open pipeline: {Object.entries(query.data.pipeline_values).map(([currency, value]) => `${Number(value).toLocaleString()} ${currency}`).join(' · ') || 'No estimated values yet'}. Estimates are not booked revenue.</p></>}
    {query.data && query.data.by_owner.length > 0 && <details className="panel mb-5 p-4"><summary className="cursor-pointer text-sm font-semibold">Team progress by owner</summary><div className="mt-3 grid gap-2 sm:grid-cols-2">{query.data.by_owner.map((r, i) => <p key={i} className="text-xs">{r.owner} ? {r.stage}: {r.count}</p>)}</div></details>}
    <section className="panel"><div className="flex flex-wrap gap-3 border-b p-4"><Input className="max-w-sm" aria-label="Search opportunities" placeholder="Search opportunities" value={q} onChange={e => { setQ(e.target.value); setPage(1) }} /><select aria-label="Filter opportunities" className="select-input" value={filter} onChange={e => { setFilter(e.target.value); setPage(1) }}>{[['all', 'All accessible'], ['mine', 'Assigned to me'], ['unassigned', 'Awaiting assignment'], ['no_action', 'No next action'], ['overdue', 'Overdue follow-ups']].map(([v, name]) => <option key={v} value={v}>{name}</option>)}</select>{stage && <Button variant="ghost" onClick={() => setStage('')}>Clear stage filter</Button>}</div>
      {query.isPending ? <Loading /> : query.error ? <ErrorState error={query.error} /> : !query.data.items.length ? <EmptyState icon={Target} title="No opportunities found" description="Create one from an organization or a campaign conversation." /> : <div className="divide-y">{query.data.items.map(o => <article key={o.id} className="flex flex-wrap items-center justify-between gap-4 p-5"><div><Link className="text-sm font-semibold text-primary underline" to={`/opportunities/${o.id}`}>{o.title}</Link><p className="mt-1 text-xs text-muted-foreground">{o.organization} · {o.owner || 'Awaiting assignment'} · <span className="capitalize">{o.stage}</span></p><p className="mt-2 text-xs">{o.next_action && !['won', 'lost'].includes(o.stage) ? `${o.next_action.title} · ${date(o.next_action.due_at)}` : ['won', 'lost'].includes(o.stage) ? 'Closed opportunity' : 'No next action scheduled'}</p></div><span className="text-xs">{o.estimated_value !== null ? `${Number(o.estimated_value).toLocaleString()} ${o.currency}` : 'Value not estimated'}{o.expected_close && <span className="block text-muted-foreground">Expected close: {o.expected_close}</span>}</span></article>)}</div>}
      {query.data && <div className="flex items-center justify-between border-t p-4 text-xs"><span>{query.data.total} opportunities · Page {page}</span><div className="flex gap-2"><Button variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><Button variant="outline" disabled={page * 20 >= query.data.total} onClick={() => setPage(page + 1)}>Next</Button></div></div>}
    </section></>
}

export function OpportunityEditor() {
  const { id } = useParams()
  const query = useQuery({ queryKey: ['opportunities', id], queryFn: () => api<Detail>(`/opportunities/${id}`), enabled: !!id })
  if (id && query.isPending) return <Loading />
  if (query.error) return <ErrorState error={query.error} />
  if (query.data && !query.data.can_edit) return <p>This opportunity is awaiting assignment or is read-only.</p>
  return <OpportunityForm key={id || 'new'} initial={query.data} />
}

function OpportunityForm({ initial }: { initial?: Opportunity }) {
  const auth = useAuth(), navigate = useNavigate(), refresh = useRefresh(), [params] = useSearchParams()
  const isManager = manager(auth.user!.roles)
  const source = params.get('source_recipient_id')
  const [search, setSearch] = useState('')
  const [form, setForm] = useState({ title: initial?.title || '', organization_id: initial?.organization_id || params.get('organization_id') || '', owner_id: '', stage: initial?.stage || 'new', estimated_value: initial?.estimated_value || '', currency: initial?.currency || 'XAF', expected_close: initial?.expected_close || '', loss_reason: initial?.loss_reason || '', notes: initial?.notes || '' })
  const orgs = useQuery({ queryKey: ['opportunities', 'organizations', search], queryFn: () => api<{ id: string; name: string }[]>(`/opportunities/organizations?q=${encodeURIComponent(search)}`), enabled: !initial && !source })
  const owners = useQuery({ queryKey: ['opportunities', 'owners'], queryFn: () => api<{ id: string; full_name: string }[]>('/opportunities/owners'), enabled: isManager && !initial })
  const save = useMutation({ mutationFn: () => {
    const { organization_id, owner_id, ...details } = form
    return send<Opportunity>(initial ? `/opportunities/${initial.id}` : '/opportunities', { ...details, estimated_value: form.estimated_value || null, expected_close: form.expected_close || null,
      ...(initial ? { version: initial.version } : { organization_id, owner_id: owner_id || null, source_recipient_id: source || null }) }, initial ? 'PUT' : 'POST')
  }, onSuccess: o => { refresh(); toast.success('Opportunity saved'); navigate(`/opportunities/${o.id}`) } })
  return <><PageHeader title={initial ? 'Edit opportunity' : 'New opportunity'} description="Record the business need. Email conversations stay in Campaigns." /><form className="panel max-w-3xl space-y-4 p-5" onSubmit={e => { e.preventDefault(); save.mutate() }}><fieldset disabled={save.isPending} className="space-y-4">
    <label className="block text-sm">Opportunity title<Input required minLength={2} maxLength={180} value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} /></label>
    {!initial && (source ? <p className="text-sm">From campaign conversation: {params.get('organization') || 'Selected company'}</p> : <><Input aria-label="Find organization" placeholder="Find organization" value={search} onChange={e => setSearch(e.target.value)} />{orgs.error && <ErrorState error={orgs.error} />}<label className="block text-sm">Organization<select aria-label="Organization" required className={selectClass} value={form.organization_id} onChange={e => setForm({ ...form, organization_id: e.target.value })}><option value="">Select organization</option>{form.organization_id && !orgs.data?.some(o => o.id === form.organization_id) && <option value={form.organization_id}>{params.get('organization') || 'Selected organization'}</option>}{orgs.data?.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label></>)}
    {!initial && (isManager ? <label className="block text-sm">Assign owner<select aria-label="Assign owner" className={selectClass} value={form.owner_id} onChange={e => setForm({ ...form, owner_id: e.target.value })}><option value="">Assign later</option>{owners.data?.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select>{owners.error && <ErrorState error={owners.error} />}</label> : <p className="text-xs text-muted-foreground">A manager or CEO will assign the owner after submission.</p>)}
    <div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm">Stage<select aria-label="Stage" className={selectClass} value={form.stage} onChange={e => setForm({ ...form, stage: e.target.value })}>{stages.map(s => <option key={s} value={s}>{s}</option>)}</select></label><label className="block text-sm">Expected close date<Input type="date" value={form.expected_close} onChange={e => setForm({ ...form, expected_close: e.target.value })} /></label><label className="block text-sm">Estimated value<Input type="number" min="0" max="99999999999999.99" step="0.01" value={form.estimated_value} onChange={e => setForm({ ...form, estimated_value: e.target.value })} /></label><label className="block text-sm">Currency<select aria-label="Currency" className={selectClass} value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })}>{['XAF', 'USD', 'EUR', 'GBP'].map(c => <option key={c}>{c}</option>)}</select></label></div>
    {form.stage === 'lost' && <label className="block text-sm">Loss reason<Textarea required maxLength={1000} value={form.loss_reason} onChange={e => setForm({ ...form, loss_reason: e.target.value })} /></label>}
    <label className="block text-sm">Requirements and internal notes<Textarea maxLength={10000} rows={5} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></label>
    {save.error && <p role="alert" className="text-sm text-destructive">{save.error.message}</p>}
    <div className="flex gap-3"><Button>Save opportunity</Button><Button asChild variant="outline"><Link to={initial ? `/opportunities/${initial.id}` : '/opportunities'}>Cancel</Link></Button></div>
  </fieldset></form></>
}

export function OpportunityDetail() {
  const { id } = useParams(), auth = useAuth(), refresh = useRefresh()
  const [owner, setOwner] = useState(''), [taskEditor, setTaskEditor] = useState<Task | 'new' | null>(null)
  const query = useQuery({ queryKey: ['opportunities', id], queryFn: () => api<Detail>(`/opportunities/${id}`) })
  const isManager = manager(auth.user!.roles)
  const owners = useQuery({ queryKey: ['opportunities', 'owners'], queryFn: () => api<{ id: string; full_name: string }[]>('/opportunities/owners'), enabled: isManager })
  const assign = useMutation({ mutationFn: () => send(`/opportunities/${id}/assign`, { owner_id: owner, version: query.data!.version }), onSuccess: () => { refresh(); toast.success('Owner assigned') }, onError: (e: Error) => toast.error(e.message) })
  const complete = useMutation({ mutationFn: (t: Task) => send(`/opportunities/${id}/tasks/${t.id}`, { title: t.title, notes: t.notes, due_at: t.due_at, version: t.version, completed: !t.completed_at }, 'PUT'), onSuccess: refresh, onError: (e: Error) => toast.error(e.message) })
  if (query.isPending) return <Loading />
  if (query.error) return <ErrorState error={query.error} />
  const o = query.data, closed = ['won', 'lost'].includes(o.stage)
  return <><Button asChild variant="ghost"><Link to="/opportunities">Back to opportunities</Link></Button><PageHeader title={o.title} description={`${o.organization} · ${o.stage} · ${o.owner || 'Awaiting assignment'}`} action={o.can_edit ? <Button asChild variant="outline"><Link to={`/opportunities/${o.id}/edit`}>Edit opportunity</Link></Button> : undefined} />
    <div className="grid items-start gap-5 xl:grid-cols-2"><div className="space-y-5"><section className="panel space-y-3 p-5"><h2 className="font-semibold">Opportunity details</h2><p className="text-sm">Estimated value: {o.estimated_value !== null ? `${Number(o.estimated_value).toLocaleString()} ${o.currency}` : 'Not estimated'}</p><p className="text-sm">Expected close: {o.expected_close || 'Not scheduled'}</p><p className="whitespace-pre-wrap break-words text-sm">{o.notes || 'No requirements recorded yet.'}</p>{o.stage === 'lost' && <p className="text-sm">Loss reason: {o.loss_reason}</p>}
      {isManager && <form className="space-y-2 border-t pt-3" onSubmit={e => { e.preventDefault(); assign.mutate() }}><label className="block text-sm">Assign owner<select aria-label="Assign owner" required className={selectClass} value={owner} onChange={e => setOwner(e.target.value)}><option value="">Choose owner</option>{owners.data?.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label>{owners.error && <ErrorState error={owners.error} />}<Button disabled={!owner || assign.isPending}>Assign owner</Button></form>}
    </section><section className="panel space-y-3 p-5"><h2 className="font-semibold">Email conversations</h2><p className="text-xs text-muted-foreground">All messages and replies stay in Email campaigns. New emails follow the existing approval process.</p>{o.campaigns.map(c => <Link key={c.id} className="block text-sm text-primary underline" to={`/campaigns/${c.id}`}>{c.name} · {c.status}</Link>)}{auth.can('campaigns.read') && o.can_edit && !closed && <Button asChild variant="outline"><Link to={`/campaigns/new?opportunity_id=${o.id}`}>Compose in Campaigns</Link></Button>}{!auth.can('campaigns.read') && <p className="text-sm">Ask the CEO for Campaigns access to view or send emails.</p>}</section></div>
    <section className="panel space-y-4 p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">Follow-up tasks</h2>{o.can_edit && !closed && <Button size="sm" onClick={() => setTaskEditor('new')}>Add task</Button>}</div>{closed && <p className="text-xs text-muted-foreground">This opportunity is closed. Open tasks are retained in history; reminders are paused.</p>}{!o.tasks.length && <p className="text-sm text-muted-foreground">No tasks yet. Set a next action and due date.</p>}{o.tasks.map(t => <article key={t.id} className="space-y-2 border-t pt-3"><h3 className={`text-sm font-medium ${t.completed_at ? 'line-through text-muted-foreground' : ''}`}>{t.title}</h3><p className="text-xs">{t.completed_at ? `Completed ${date(t.completed_at)}` : `Due ${date(t.due_at)}`}</p><p className="whitespace-pre-wrap text-xs text-muted-foreground">{t.notes}</p>{o.can_edit && <div className="flex gap-2"><Button size="sm" variant="outline" disabled={complete.isPending} onClick={() => complete.mutate(t)}>{t.completed_at ? 'Reopen task' : 'Complete task'}</Button><Button size="sm" variant="ghost" onClick={() => setTaskEditor(t)}>Edit task</Button></div>}</article>)}{taskEditor && <TaskForm key={taskEditor === 'new' ? 'new' : taskEditor.id} opportunityId={o.id} task={taskEditor === 'new' ? undefined : taskEditor} onClose={() => setTaskEditor(null)} />}</section></div>
    <section className="panel mt-5 p-5"><h2 className="font-semibold">Activity history</h2><ul className="mt-3 divide-y">{o.activity.map(a => <li key={a.id} className="py-3 text-xs"><p>{a.actor_name} · {a.action.replaceAll('opportunity.', '').replaceAll('_', ' ')} · {date(a.created_at)}</p>{a.details.stage != null && <p className="mt-1 text-muted-foreground">Stage: {String(a.details.from_stage)} → {String(a.details.stage)}</p>}{a.details.title != null && <p className="mt-1">{String(a.details.title)}</p>}</li>)}</ul></section>
  </>
}

function TaskForm({ opportunityId, task, onClose }: { opportunityId: string; task?: Task; onClose: () => void }) {
  const refresh = useRefresh()
  const local = task ? new Date(new Date(task.due_at).getTime() - new Date(task.due_at).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : ''
  const [title, setTitle] = useState(task?.title || ''), [notes, setNotes] = useState(task?.notes || ''), [due, setDue] = useState(local)
  const save = useMutation({ mutationFn: () => send(`/opportunities/${opportunityId}/tasks${task ? `/${task.id}` : ''}`, { title, notes, due_at: new Date(due).toISOString(), ...(task ? { version: task.version, completed: !!task.completed_at } : {}) }, task ? 'PUT' : 'POST'), onSuccess: () => { refresh(); onClose(); toast.success('Task saved') } })
  return <form className="space-y-3 rounded-lg border p-4" onSubmit={e => { e.preventDefault(); save.mutate() }}><h3 className="text-sm font-semibold">{task ? 'Edit task' : 'New follow-up task'}</h3><label className="block text-sm">Task title<Input required minLength={2} maxLength={180} value={title} onChange={e => setTitle(e.target.value)} /></label><label className="block text-sm">Due date and time<Input required type="datetime-local" value={due} onChange={e => setDue(e.target.value)} /></label><label className="block text-sm">Task notes<Textarea maxLength={5000} value={notes} onChange={e => setNotes(e.target.value)} /></label>{save.error && <p role="alert" className="text-sm text-destructive">{save.error.message}</p>}<Button disabled={save.isPending}>Save task</Button><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button></form>
}
