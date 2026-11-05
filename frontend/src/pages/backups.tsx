import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, CalendarClock, Download, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Navigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, Loading, PageHeader } from '@/components/shared'
import { useAuth } from '@/features/auth/auth-context'
import { useOnline } from '@/hooks/use-online'
import { api, send } from '@/lib/api'
import { cn } from '@/lib/utils'

type BackupRun = {
  id: string; created_at: string; finished_at: string | null; trigger: 'manual' | 'scheduled'
  status: 'queued' | 'running' | 'completed' | 'failed' | 'expired'; size_bytes: number | null; error: string | null
}
type Overview = { next_run: string; heartbeat: string | null; issue: string | null; runs: BackupRun[] }
const formatDate = (value: string) => new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Africa/Douala', dateStyle: 'medium', timeStyle: 'short',
}).format(new Date(value))

export default function BackupsPage() {
  const auth = useAuth()
  return auth.user?.roles.includes('CEO') ? <BackupWorkspace /> : <Navigate to="/" replace />
}

function BackupWorkspace() {
  const client = useQueryClient()
  const online = useOnline()
  const query = useQuery({ queryKey: ['backups'], queryFn: () => api<Overview>('/backups'), refetchInterval: 5000 })
  const create = useMutation({
    mutationFn: () => send('/backups'),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ['backups'] }); toast.success('Backup queued. You can keep working while it runs.') },
    onError: error => { toast.error(error.message); void client.invalidateQueries({ queryKey: ['backups'] }) },
  })
  if (query.isPending) return <Loading label="Loading backups…" />
  if (query.error) return <ErrorState error={query.error} retry={() => { void query.refetch() }} />
  const data = query.data
  const active = data.runs.some(run => run.status === 'queued' || run.status === 'running')
  const running = data.runs.some(run => run.status === 'running')
  const workerUnavailable = !running && (!data.heartbeat || Date.now() - new Date(data.heartbeat).getTime() > 90_000)
  const latest = data.runs.find(run => run.status === 'completed')
  return <>
    <PageHeader eyebrow="Workspace protection" title="Backup" description="Protect your business records with scheduled and on-demand backups."
      action={<Button disabled={!online || active || create.isPending || !!data.issue || workerUnavailable} onClick={() => create.mutate()}><Archive className="size-4" />{active ? 'Backup in progress' : create.isPending ? 'Queuing backup…' : 'Back up now'}</Button>} />
    <div className="space-y-5">
      {(data.issue || workerUnavailable) && <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-xs leading-6 text-amber-900">{data.issue || 'The backup worker is not responding. Ask your administrator to check the server.'}</div>}
      <div className="grid gap-5 md:grid-cols-2">
        <section className="panel p-6"><div className="flex items-center gap-3"><CalendarClock className="size-5 text-primary" /><h2 className="text-sm font-semibold">Automatic backup</h2></div><p className="mt-4 text-lg font-semibold">Every Monday at 12:00 noon</p><p className="mt-2 text-xs text-muted-foreground">Cameroon time · Africa/Douala (UTC+1)</p><p className="mt-4 text-xs">Next scheduled: <span className="font-medium">{formatDate(data.next_run)}</span></p><p className="mt-2 text-xs leading-6 text-muted-foreground">The server must be running. If a scheduled backup is missed, one catch-up backup runs when the server returns.</p></section>
        <section className="panel p-6"><div className="flex items-center gap-3"><ShieldCheck className="size-5 text-emerald-600" /><h2 className="text-sm font-semibold">Latest verified backup</h2></div><p className="mt-4 text-lg font-semibold">{latest ? formatDate(latest.finished_at!) : 'No successful backups yet'}</p><p className="mt-2 text-xs leading-6 text-muted-foreground">Encrypted and checked before it becomes available. The eight most recent successful backups are kept on this server.</p><p className="mt-3 text-xs leading-6 text-muted-foreground">Download a copy and its checksum to secure storage on another device for protection against server loss.</p></section>
      </div>
      <section className="panel overflow-hidden"><div className="border-b px-6 py-5"><h2 className="text-sm font-semibold">Backup history</h2><p className="mt-1 text-xs text-muted-foreground">Latest 50 attempts · All times are Cameroon time</p></div>
        {!data.runs.length ? <EmptyState icon={Archive} title="Your first backup starts here" description="Create a backup now, or leave the server running for the next Monday schedule." /> : <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-muted-foreground"><tr><th className="px-6 py-3">Started</th><th className="px-4 py-3">Source</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Size</th><th className="px-6 py-3">Files</th></tr></thead><tbody className="divide-y">{data.runs.map(run => <tr key={run.id}><td className="whitespace-nowrap px-6 py-4">{formatDate(run.created_at)}</td><td className="px-4 py-4 capitalize">{run.trigger}</td><td className="px-4 py-4"><span className={cn('inline-flex rounded-md px-2 py-1 text-[10px] font-medium capitalize', run.status === 'completed' ? 'bg-emerald-50 text-emerald-700' : run.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-600')}>{run.status === 'completed' ? 'Verified' : run.status}</span>{run.error && <p className="mt-2 max-w-xs text-[11px] leading-5 text-red-700">{run.error}</p>}</td><td className="whitespace-nowrap px-4 py-4 text-muted-foreground">{run.size_bytes === null ? '—' : `${(Number(run.size_bytes) / 1024 / 1024).toFixed(2)} MB`}</td><td className="px-6 py-4">{run.status === 'completed' ? <div className="flex items-center gap-3"><a className="inline-flex items-center gap-1 font-medium text-primary hover:underline" href={`/api/backups/${run.id}/download`} download aria-label={`Download backup from ${formatDate(run.created_at)}`}><Download className="size-3.5" />Backup</a><a className="text-muted-foreground hover:underline" href={`/api/backups/${run.id}/download?checksum=true`} download aria-label={`Download checksum from ${formatDate(run.created_at)}`}>Checksum</a></div> : <span className="text-muted-foreground">—</span>}</td></tr>)}</tbody></table></div>}
      </section>
      <section className="rounded-xl border border-dashed bg-slate-50 p-6"><h2 className="text-sm font-semibold">Recovery</h2><p className="mt-2 text-xs leading-6 text-muted-foreground">Backups contain your application database, including business records, accounts, and history. Keep encryption keys and deployment configuration separately in secure storage. An administrator can restore into a separate empty database and verify it before switching the system over.</p></section>
    </div>
  </>
}
