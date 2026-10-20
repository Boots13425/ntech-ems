import { useEffect, useState } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { Download, RefreshCw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface InstallEvent extends Event { prompt(): Promise<void>; userChoice: Promise<{ outcome: string }> }
export function PwaControls() {
  const [install, setInstall] = useState<InstallEvent | null>(null)
  const [dismissed, setDismissed] = useState(false)
  const [registration, setRegistration] = useState<ServiceWorkerRegistration>()
  const { needRefresh: [needRefresh, setNeedRefresh], updateServiceWorker } = useRegisterSW({ onRegisteredSW: (_, reg) => setRegistration(reg) })
  useEffect(() => { const handle = (event: Event) => { event.preventDefault(); setInstall(event as InstallEvent) }; const installed = () => setInstall(null); window.addEventListener('beforeinstallprompt', handle); window.addEventListener('appinstalled', installed); return () => { window.removeEventListener('beforeinstallprompt', handle); window.removeEventListener('appinstalled', installed) } }, [])
  useEffect(() => { if (!registration) return; const timer = window.setInterval(() => { if (navigator.onLine) void registration.update().catch(() => {}) }, 60 * 60 * 1000); return () => window.clearInterval(timer) }, [registration])
  if (!needRefresh && (!install || dismissed)) return null
  return <aside aria-label="Application installation and updates" className="fixed right-4 bottom-4 left-4 z-50 flex items-center gap-4 rounded-xl border bg-white p-4 shadow-xl sm:left-auto sm:max-w-md"><span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-primary">{needRefresh ? <RefreshCw className="size-5" /> : <Download className="size-5" />}</span><div className="flex-1"><p className="text-xs font-semibold">{needRefresh ? 'A workspace update is ready' : 'Keep your workspace close'}</p><p className="mt-1 text-[10px] leading-5 text-muted-foreground">{needRefresh ? 'Save your work before reloading.' : 'Install NTECH EMS for quick access from this device.'}</p><Button size="sm" className="mt-2 h-7 text-[10px]" onClick={async () => { if (needRefresh) await updateServiceWorker(true); else if (install) { await install.prompt(); await install.userChoice; setInstall(null) } }}>{needRefresh ? 'Reload and update' : 'Install application'}</Button></div><button aria-label="Dismiss" onClick={() => { setNeedRefresh(false); setDismissed(true) }} className="self-start rounded p-1 text-slate-400"><X className="size-4" /></button></aside>
}
