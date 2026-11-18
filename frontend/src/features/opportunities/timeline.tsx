import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { api, send } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ErrorState, Loading } from '@/components/shared'

const kinds = { initial_meeting: 'Initial meeting', follow_up_meeting: 'Follow-up meeting', call: 'Phone call', proposal: 'Proposal', agreement: 'Agreement', progress: 'Progress update', note: 'Note', correction: 'Correction' }
type Kind = keyof typeof kinds
type Entry = { id: string; action: string; occurred_at: string; created_at: string; actor_name: string; details: { kind?: Kind; title?: string; notes?: string; participants?: string; outcome?: string; stage?: string; from_stage?: string; owner?: string; previous_owner?: string; due_at?: string; status?: string; completed?: boolean; campaign_id?: string; campaign_name?: string; operation?: string; next_task?: { title: string; due_at: string }; previous?: { due_at: string; status: string; notes: string; title: string }; changes?: Record<string, { from: string | null; to: string | null }> } }
const when = (value: string) => new Date(value).toLocaleString()
const words = (value: string) => value.replaceAll('_', ' ')
const localNow = () => { const now = new Date(); return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
// getRandomValues also works on the existing HTTP LAN installation.
function entryUuid() {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export function OpportunityTimeline({ id, canEdit, closed, canReadCampaigns }: { id: string; canEdit: boolean; closed: boolean; canReadCampaigns: boolean }) {
  const [page, setPage] = useState(1), [kind, setKind] = useState('all'), [adding, setAdding] = useState(false)
  const query = useQuery({ queryKey: ['opportunities', id, 'timeline', page, kind], queryFn: () => api<{ items: Entry[]; total: number; page_size: number }>(`/opportunities/${id}/timeline?page=${page}&kind=${kind}`), refetchInterval: 30_000 })
  return <section className="panel mt-5 p-5" aria-label="Opportunity logbook">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold">Opportunity timeline</h2><p className="mt-1 text-sm text-muted-foreground">The shared logbook: conversations, decisions, progress, and next steps. Newest events first.</p></div>{canEdit && <Button onClick={() => setAdding(!adding)}>{adding ? 'Close entry form' : 'Record activity'}</Button>}</div>
    {!canEdit && <p className="mt-3 text-xs text-muted-foreground">You can follow progress here. The assigned owner and management record updates.</p>}
    {adding && canEdit && <LogForm id={id} closed={closed} onSaved={() => { setAdding(false); setPage(1); setKind('all') }} />}
    <div className="my-5 flex flex-wrap items-center justify-between gap-3"><label className="text-sm">Show entries<select className="select-input ml-2" value={kind} onChange={e => { setKind(e.target.value); setPage(1) }}><option value="all">All activity</option><option value="log">Staff logbook</option><option value="automatic">Automatic updates</option></select></label><span className="text-xs text-muted-foreground">{query.data?.total ?? '…'} entries · Dates shown in your local time</span></div>
    {query.isPending ? <Loading /> : query.error ? <ErrorState error={query.error} /> : <>
      {!query.data.items.length && <p className="py-5 text-sm text-muted-foreground">No entries in this view yet.</p>}
      <ol className="ml-2 space-y-6 border-l-2 border-slate-200 pl-6">{query.data.items.map(entry => {
        const d = entry.details, manual = entry.action === 'opportunity.log_entry'
        return <li key={entry.id} className="relative min-w-0"><span className={`absolute -left-[31px] top-1 size-3 rounded-full border-2 border-white ${manual ? 'bg-primary' : 'bg-slate-400'}`} />
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground"><span className="font-semibold text-foreground">{manual && d.kind ? kinds[d.kind] : words(entry.action.replace('opportunity.', ''))}</span><time dateTime={entry.occurred_at}>{when(entry.occurred_at)}</time><span>{entry.actor_name}</span>{!manual && <span>Automatic</span>}</div>
          {d.title && <p className="mt-2 break-words font-medium">{d.title}</p>}
          {d.participants && <p className="mt-2 break-words text-sm"><strong>Participants:</strong> {d.participants}</p>}
          {d.notes && <p className="mt-2 whitespace-pre-wrap break-words text-sm">{d.notes}</p>}
          {d.outcome && <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm"><strong>Outcome / agreement</strong><p className="mt-1 whitespace-pre-wrap break-words">{d.outcome}</p></div>}
          {d.next_task && <p className="mt-3 break-words text-sm"><strong>Follow-up scheduled:</strong> {d.next_task.title} · {when(d.next_task.due_at)}</p>}
          {d.status && <p className="mt-2 text-sm capitalize">{d.previous?.status ? `${words(d.previous.status)} → ` : ''}{words(d.status)}</p>}
          {d.due_at && <p className="mt-1 text-xs text-muted-foreground">Due: {when(d.due_at)}{d.previous?.due_at && d.previous.due_at !== d.due_at ? ` (previously ${when(d.previous.due_at)})` : ''}</p>}
          {d.previous && (d.previous.title !== d.title || d.previous.notes !== d.notes) && <details className="mt-2 text-xs"><summary className="cursor-pointer">Previous task details</summary><p className="mt-2 whitespace-pre-wrap break-words">{d.previous.title}{'\n'}{d.previous.notes}</p></details>}
          {d.owner && <p className="mt-2 text-sm">Owner: {d.previous_owner ? `${d.previous_owner} → ` : ''}{d.owner}</p>}
          {d.changes ? <dl className="mt-2 space-y-2 text-sm">{Object.entries(d.changes).map(([field, change]) => <div key={field}><dt className="font-medium capitalize">{words(field)}</dt><dd className="whitespace-pre-wrap break-words text-muted-foreground">{change.from || 'Not set'} → {change.to || 'Not set'}</dd></div>)}</dl> : d.stage && <p className="mt-2 text-sm capitalize">Stage: {d.from_stage && d.from_stage !== d.stage ? `${d.from_stage} → ` : ''}{d.stage}</p>}
          {d.campaign_name && <p className="mt-2 text-sm">{d.campaign_name} · {d.operation && words(d.operation)} {canReadCampaigns && d.campaign_id && <Link className="text-primary underline" to={`/campaigns/${d.campaign_id}`}>Open campaign</Link>}</p>}
          {manual && <p className="mt-2 text-xs text-muted-foreground">Recorded {when(entry.created_at)}. Corrections are added as new entries to preserve history.</p>}
        </li>
      })}</ol>
      <div className="mt-6 flex items-center justify-between border-t pt-4"><span className="text-xs">Page {page}</span><div className="flex gap-2"><Button variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>Newer entries</Button><Button variant="outline" disabled={page * query.data.page_size >= query.data.total} onClick={() => setPage(page + 1)}>Older entries</Button></div></div>
    </>}
  </section>
}

function LogForm({ id, closed, onSaved }: { id: string; closed: boolean; onSaved: () => void }) {
  const client = useQueryClient()
  const [entryId] = useState(entryUuid)
  const [form, setForm] = useState({ kind: 'initial_meeting', title: '', notes: '', occurred_at: localNow(), participants: '', outcome: '', follow: false, taskTitle: '', due: '' })
  const save = useMutation({ mutationFn: () => send(`/opportunities/${id}/timeline`, { id: entryId, kind: form.kind, title: form.title.trim(), notes: form.notes.trim(), occurred_at: new Date(form.occurred_at).toISOString(), participants: form.participants, outcome: form.outcome,
    next_task: form.follow && !closed ? { title: form.taskTitle.trim(), due_at: new Date(form.due).toISOString(), notes: '' } : null }), onSuccess: () => { void client.invalidateQueries({ queryKey: ['opportunities'] }); void client.invalidateQueries({ queryKey: ['notifications'] }); toast.success('Activity recorded'); onSaved() } })
  return <form className="mt-5 rounded-xl border bg-slate-50 p-4" onSubmit={e => { e.preventDefault(); save.mutate() }}><fieldset disabled={save.isPending} className="space-y-4"><h3 className="font-semibold">Record activity</h3>
    <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Activity type<select className="select-input w-full" value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value })}>{Object.entries(kinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label className="text-sm">When it happened<Input required type="datetime-local" value={form.occurred_at} onChange={e => setForm({ ...form, occurred_at: e.target.value })} /></label></div>
    <label className="block text-sm">Activity title<Input required minLength={2} maxLength={180} value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Discussed the customer's requirements" /></label>
    <label className="block text-sm">Participants<Input maxLength={1000} value={form.participants} onChange={e => setForm({ ...form, participants: e.target.value })} placeholder="Who attended or was contacted?" /></label>
    <label className="block text-sm">What happened / current progress<Textarea required rows={5} maxLength={10000} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></label>
    <label className="block text-sm">Outcome or agreement<Textarea rows={3} maxLength={5000} value={form.outcome} onChange={e => setForm({ ...form, outcome: e.target.value })} placeholder="Decisions, commitments, blockers, or agreed terms" /></label>
    {!closed && <><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.follow} onChange={e => setForm({ ...form, follow: e.target.checked })} />Schedule a follow-up from this entry</label>{form.follow && <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Next action<Input required minLength={2} maxLength={180} value={form.taskTitle} onChange={e => setForm({ ...form, taskTitle: e.target.value })} /></label><label className="text-sm">Follow-up due<Input required type="datetime-local" value={form.due} onChange={e => setForm({ ...form, due: e.target.value })} /></label><p className="text-xs text-muted-foreground sm:col-span-2">Assigned automatically to the opportunity owner. Due and overdue reminders are automatic.</p></div>}</>}
    {save.error && <p role="alert" className="text-sm text-destructive">{save.error.message}</p>}
    <Button disabled={save.isPending}>Save activity</Button>
  </fieldset></form>
}
