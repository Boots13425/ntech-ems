import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Check, ChevronLeft, ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { useAuth } from '@/features/auth/auth-context'
import { api, send } from '@/lib/api'

type Notification = { id: string; title: string; message: string; path: string; created_at: string; read_at: string | null }
type Inbox = { items: Notification[]; unread_count: number; total: number; page: number; page_size: number }

export function Notifications() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const scope = ['notifications', user!.id, user!.roles.join(','), [...user!.permissions].sort().join(',')]
  // The count always covers the entire inbox, independently of pagination/filter.
  const count = useQuery({ queryKey: [...scope, 'count'], queryFn: () => api<Inbox>('/notifications?page_size=1'), refetchInterval: 15_000 })
  const inbox = useQuery({ queryKey: [...scope, page, unreadOnly], queryFn: () => api<Inbox>(`/notifications?page=${page}&unread_only=${unreadOnly}`), enabled: open, refetchInterval: 15_000 })
  const mark = useMutation({
    mutationFn: (id: string | null) => send(id ? `/notifications/${id}/read` : '/notifications/read-all'),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ['notifications'] }) },
    onError: (error: Error) => toast.error(error.message),
  })
  async function openNotification(item: Notification) {
    if (!item.read_at) {
      try { await mark.mutateAsync(item.id) } catch { return }
    }
    setOpen(false)
    navigate(item.path)
  }
  const unread = count.isError ? 0 : count.data?.unread_count ?? 0
  return <Dialog open={open} onOpenChange={value => { setOpen(value); if (value) { setPage(1); void count.refetch() } }}>
    <DialogTrigger asChild><Button variant="ghost" size="icon" className="relative" aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}>
      <Bell className="size-[18px] text-slate-500" />
      {unread > 0 && <span className="absolute -right-1 -top-1 rounded-full bg-primary px-1.5 text-[10px] text-white" aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}
    </Button></DialogTrigger>
    <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-xl">
      <DialogHeader><DialogTitle>Notifications</DialogTitle><DialogDescription>Campaign updates and account alerts addressed to you. Updates refresh automatically.</DialogDescription></DialogHeader>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={unreadOnly} onChange={event => { setUnreadOnly(event.target.checked); setPage(1) }} />Unread only</label>
        <Button size="sm" variant="outline" disabled={mark.isPending || !unread} onClick={() => mark.mutate(null)}><Check className="size-4" />Mark all as read</Button>
      </div>
      {inbox.isPending ? <p role="status" className="py-8 text-center text-sm">Loading notifications…</p> : inbox.isError ? <div role="alert" className="space-y-3 py-4 text-sm"><p>{inbox.error.message}</p><Button variant="outline" onClick={() => { void inbox.refetch() }}>Try again</Button></div> : <>
        {!inbox.data.items.length ? <p className="py-8 text-center text-sm text-muted-foreground">{unreadOnly ? 'No unread notifications.' : 'No notifications yet.'}</p> : <ul className="divide-y">{inbox.data.items.map(item => <li key={item.id} className={`py-4 ${item.read_at ? '' : 'rounded-md bg-blue-50/60 px-3'}`}>
          <button className="w-full space-y-1.5 text-left" disabled={mark.isPending} onClick={() => { void openNotification(item) }}>
            <span className="flex items-center gap-2 text-sm font-semibold">{!item.read_at && <span className="size-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}{item.title}</span>
            <span className="block break-words text-xs leading-5 text-muted-foreground">{item.message}</span>
            <time className="block text-[10px] text-muted-foreground" dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>
          </button>
          {!item.read_at && <Button className="mt-2" size="sm" variant="ghost" disabled={mark.isPending} onClick={() => mark.mutate(item.id)}>Mark as read</Button>}
        </li>)}</ul>}
        <div className="flex items-center justify-between border-t pt-3 text-xs"><span>{inbox.data.total} notifications · Page {page}</span><div className="flex gap-2"><Button size="icon" variant="outline" aria-label="Previous notifications" disabled={page === 1} onClick={() => setPage(page - 1)}><ChevronLeft className="size-4" /></Button><Button size="icon" variant="outline" aria-label="Next notifications" disabled={page * inbox.data.page_size >= inbox.data.total} onClick={() => setPage(page + 1)}><ChevronRight className="size-4" /></Button></div></div>
      </>}
    </DialogContent>
  </Dialog>
}
