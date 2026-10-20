import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bell, Building2, ChartNoAxesCombined, ChevronDown, ChevronsLeft, ChevronsRight, FolderKanban, Handshake, LayoutDashboard, LogOut, Mail, Menu, Search, Settings, ShieldCheck, Target, Users, UsersRound, WifiOff } from 'lucide-react'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Brand } from '@/components/shared'
import { useAuth } from '@/features/auth/auth-context'
import { useOnline } from '@/hooks/use-online'
import { api } from '@/lib/api'
import { cn, initials } from '@/lib/utils'

const groups = [
  { label: 'Workspace', items: [
    { to: '/', title: 'Overview', icon: LayoutDashboard, permission: 'dashboard.read' },
    { to: '/organizations', title: 'Organizations', icon: Building2, permission: 'organizations.read' },
    { to: '/partners', title: 'Partners', icon: Handshake, permission: 'partners.read' },
    { to: '/customers', title: 'Customers', icon: UsersRound, permission: 'customers.read' },
  ] },
  { label: 'Operations', items: [
    { to: '/staff', title: 'Staff management', icon: Users, permission: 'staff.read' },
    { to: '/campaigns', title: 'Email campaigns', icon: Mail, permission: 'campaigns.read' },
    { to: '/opportunities', title: 'Opportunities', icon: Target, permission: 'opportunities.read' },
    { to: '/projects', title: 'Projects', icon: FolderKanban, permission: 'projects.read' },
  ] },
  { label: 'Intelligence', items: [{ to: '/reports', title: 'Reports', icon: ChartNoAxesCombined, permission: 'reports.read' }] },
]
function Navigation({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const auth = useAuth()
  return <nav aria-label="Main navigation" className="space-y-7 px-3">{groups.map(group => { const items = group.items.filter(item => auth.can(item.permission)); if (!items.length) return null; return <div key={group.label}>{!collapsed && <p className="mb-2.5 px-3 text-[9px] font-semibold tracking-[.17em] text-slate-500 uppercase">{group.label}</p>}<div className="space-y-1">{items.map(item => <NavLink key={item.to} to={item.to} end={item.to === '/'} onClick={onNavigate} title={collapsed ? item.title : undefined} className={({ isActive }) => cn('flex min-h-10 items-center gap-3 rounded-lg px-3 text-[12px] font-medium transition-colors', collapsed && 'justify-center px-0', isActive ? 'bg-[#294164] text-white shadow-sm' : 'text-slate-400 hover:bg-white/5 hover:text-white')}><item.icon className="size-[17px] shrink-0" strokeWidth={1.7} />{!collapsed && item.title}</NavLink>)}</div></div> })}</nav>
}
export default function AppLayout() {
  const auth = useAuth()
  const online = useOnline()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [mobile, setMobile] = useState(false)
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<{ status: string }>('/health'), retry: false, refetchInterval: 60_000 })
  const page = [...groups.flatMap(g => g.items), { to: '/settings', title: 'Settings' }].find(i => i.to !== '/' && location.pathname.startsWith(i.to))?.title || 'Overview'
  const healthy = health.data?.status === 'ready'
  const sidebarBottom = <div className="mt-auto space-y-3 border-t border-white/8 px-3 pt-4 pb-5"><NavLink to="/settings" className={({ isActive }) => cn('flex h-10 items-center gap-3 rounded-lg px-3 text-xs', isActive ? 'bg-[#294164] text-white' : 'text-slate-400 hover:bg-white/5', collapsed && 'justify-center px-0')} title="Settings"><Settings className="size-[17px]" />{!collapsed && 'Settings'}</NavLink>{!collapsed && <div className="mx-2 rounded-lg border border-white/8 bg-white/3 px-3 py-3"><div className="flex items-center gap-2 text-[10px] text-slate-300"><span className={cn('size-1.5 rounded-full', healthy ? 'bg-emerald-400' : 'bg-amber-400')} />{health.isPending ? 'Checking connection' : healthy ? 'Database connected' : 'Connection needs attention'}</div><p className="mt-1.5 text-[9px] text-slate-500">NTECH EMS · Foundation v0.1</p></div>}</div>
  return <div className="min-h-dvh"><a href="#main-content" className="sr-only fixed top-2 left-2 z-50 rounded-lg bg-white p-3 focus:not-sr-only">Skip to content</a>
    <aside className={cn('fixed inset-y-0 left-0 z-30 hidden flex-col bg-[#14213a] transition-[width] lg:flex', collapsed ? 'w-[76px]' : 'w-[238px]')}><div className={cn('flex h-[88px] items-center px-6', collapsed && 'justify-center px-0')}><Link to="/" aria-label="NTECH EMS overview"><Brand dark compact={collapsed} /></Link></div><div className="flex-1 overflow-y-auto pt-4"><Navigation collapsed={collapsed} /></div>{sidebarBottom}<button onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} className="absolute top-[100px] -right-3 flex size-6 items-center justify-center rounded-full border bg-white text-slate-500 shadow-sm">{collapsed ? <ChevronsRight className="size-3" /> : <ChevronsLeft className="size-3" />}</button></aside>
    <div className={cn('transition-[margin] lg:ml-[238px]', collapsed && 'lg:ml-[76px]')}><header className="sticky top-0 z-20 flex h-[72px] items-center justify-between gap-3 border-b bg-white/95 px-4 backdrop-blur-sm sm:px-7 xl:px-10"><div className="flex min-w-0 items-center gap-3"><Dialog open={mobile} onOpenChange={setMobile}><DialogTrigger asChild><Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation"><Menu className="size-5" /></Button></DialogTrigger><DialogContent className="inset-y-0 left-0 h-dvh w-[280px] max-w-[85vw] translate-x-0 translate-y-0 rounded-none border-0 bg-[#14213a] p-0 text-white"><DialogTitle className="sr-only">Workspace navigation</DialogTitle><DialogDescription className="sr-only">Navigate your NTECH EMS workspace.</DialogDescription><div className="pt-8 pb-7 pl-6"><Brand dark /></div><Navigation onNavigate={() => setMobile(false)} /><Link to="/settings" onClick={() => setMobile(false)} className="m-6 flex items-center gap-3 text-sm text-slate-300"><Settings className="size-4" />Settings</Link></DialogContent></Dialog><span className="hidden text-xs text-slate-400 sm:inline">Workspace</span><span className="hidden text-slate-300 sm:inline">/</span><span className="truncate text-xs font-medium">{page}</span></div>
    <div className="flex items-center gap-2 sm:gap-4">{auth.can('organizations.read') && <form role="search" className="hidden items-center gap-2 rounded-lg border border-transparent bg-slate-50 px-3 py-2 focus-within:border-input md:flex" onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); navigate(`/organizations?q=${encodeURIComponent(String(data.get('q') || ''))}`) }}><Search className="size-3.5 text-slate-400" /><input name="q" aria-label="Search workspace organizations" placeholder="Search organizations…" className="w-40 bg-transparent text-xs outline-none xl:w-48" /><kbd className="hidden text-[9px] text-slate-400 xl:block">↵</kbd></form>}
    <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label="Notifications"><Bell className="size-[18px] text-slate-500" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-72"><DropdownMenuLabel>Notifications</DropdownMenuLabel><DropdownMenuSeparator /><div className="px-3 py-6 text-center"><Bell className="mx-auto mb-3 size-6 text-slate-300" /><p className="text-sm font-medium">Notifications are upcoming</p><p className="mt-2 text-xs leading-5 text-muted-foreground">Assignments and approval alerts will appear here when those workflows are available.</p></div></DropdownMenuContent></DropdownMenu>
    <div className="h-6 border-l" /><DropdownMenu><DropdownMenuTrigger asChild><button className="flex items-center gap-2.5 rounded-lg py-1 text-left"><span className="flex size-8 items-center justify-center rounded-full bg-[#e9eff8] text-[10px] font-semibold text-primary">{initials(auth.user!.full_name)}</span><div className="hidden sm:block"><p className="max-w-32 truncate text-xs font-semibold">{auth.user!.full_name}</p><p className="mt-0.5 text-[10px] text-muted-foreground">{auth.user!.roles.join(', ')}</p></div><ChevronDown className="size-3.5 text-slate-400" /></button></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-56"><DropdownMenuLabel className="break-all text-xs">{auth.user!.email}</DropdownMenuLabel><DropdownMenuSeparator /><DropdownMenuItem onClick={() => navigate('/settings')}><ShieldCheck className="size-4" />Account & security</DropdownMenuItem><DropdownMenuItem onClick={() => auth.logout().catch(error => toast.error(error.message))}><LogOut className="size-4" />Sign out</DropdownMenuItem></DropdownMenuContent></DropdownMenu></div></header>
    {!online && <div role="status" className="flex items-center justify-center gap-2 bg-amber-50 px-4 py-2 text-xs text-amber-900"><WifiOff className="size-4" />You’re offline. Reconnect to access and update business records.</div>}
    <main id="main-content" className="mx-auto max-w-[1600px] px-4 py-7 sm:px-7 lg:py-9 xl:px-10"><Outlet /></main><footer className="mx-4 mt-5 flex flex-wrap items-center justify-between gap-2 border-t py-5 text-[10px] text-slate-400 sm:mx-7 xl:mx-10"><span>© {new Date().getFullYear()} ETS-NTECH · Internal workspace</span><span className="flex items-center gap-1.5"><ShieldCheck className="size-3" />Secure access · Africa/Douala</span></footer></div>
  </div>
}
