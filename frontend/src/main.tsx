import React, { lazy, Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { AuthProvider, useAuth } from '@/features/auth/auth-context'
import { ChangePassword, MfaGate } from '@/features/auth/mfa'
import { ErrorState, Loading } from '@/components/shared'
import { PwaControls } from '@/components/pwa-controls'
import { Button } from '@/components/ui/button'
import './index.css'

const Login = lazy(() => import('@/features/auth/login'))
const Layout = lazy(() => import('@/layouts/app-layout'))
const Dashboard = lazy(() => import('@/pages/dashboard'))
const Organizations = lazy(() => import('@/pages/organizations'))
const OrganizationDetail = lazy(() => import('@/pages/organization-detail'))
const Staff = lazy(() => import('@/pages/staff'))
const Settings = lazy(() => import('@/pages/settings'))
const Campaigns = lazy(() => import('@/pages/campaigns'))
const CampaignEditor = lazy(() => import('@/pages/campaigns').then(m => ({ default: m.CampaignEditor })))
const CampaignDetail = lazy(() => import('@/pages/campaigns').then(m => ({ default: m.CampaignDetail })))
const Templates = lazy(() => import('@/pages/campaigns').then(m => ({ default: m.Templates })))
const Opportunities = lazy(() => import('@/pages/opportunities'))
const OpportunityEditor = lazy(() => import('@/pages/opportunities').then(m => ({ default: m.OpportunityEditor })))
const OpportunityDetail = lazy(() => import('@/pages/opportunities').then(m => ({ default: m.OpportunityDetail })))
const Upcoming = lazy(() => import('@/pages/upcoming'))
const client = new QueryClient({ defaultOptions: { queries: { staleTime: 20_000, retry: 1 } } })

function Protected() {
  const auth = useAuth()
  if (auth.loading) return <Loading />
  if (auth.error) return <main className="mx-auto max-w-lg p-8"><ErrorState error={auth.error} retry={auth.retry} /></main>
  if (!auth.user) return <Navigate to="/login" replace />
  if (auth.user.session_state !== 'authenticated' || auth.recoveryCodes.length) return <MfaGate />
  if (auth.user.must_change_password) return <main className="mx-auto max-w-xl px-5 py-16"><ChangePassword required /><Button variant="ghost" className="mt-4" onClick={() => { void auth.logout() }}>Sign out</Button></main>
  return <Outlet />
}
function Permission({ name }: { name: string }) { const auth = useAuth(); return auth.can(name) ? <Outlet /> : <section className="panel p-8"><h1 className="text-xl font-semibold">Access not assigned</h1><p className="mt-3 text-sm text-muted-foreground">Your account does not have access to this module. Contact your administrator if your responsibilities have changed.</p></section> }
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? <main className="mx-auto max-w-lg p-10"><h1 className="text-2xl font-semibold">The workspace couldn’t open</h1><p className="my-4 text-sm text-muted-foreground">Refresh the application to try again. Unsaved changes may be lost.</p><Button onClick={() => location.reload()}>Reload workspace</Button></main> : this.props.children }
}
function App() { return <ErrorBoundary><QueryClientProvider client={client}><AuthProvider><BrowserRouter><Suspense fallback={<Loading />}><Routes><Route path="/login" element={<Login />} /><Route element={<Protected />}><Route element={<Layout />}><Route element={<Permission name="dashboard.read" />}><Route index element={<Dashboard />} /></Route><Route element={<Permission name="organizations.read" />}><Route path="organizations" element={<Organizations />} /><Route path="organizations/:id" element={<OrganizationDetail />} /></Route><Route element={<Permission name="partners.read" />}><Route path="partners" element={<Organizations classification="partner" />} /></Route><Route element={<Permission name="customers.read" />}><Route path="customers" element={<Organizations classification="customer" />} /></Route><Route element={<Permission name="staff.read" />}><Route path="staff" element={<Staff />} /></Route><Route element={<Permission name="campaigns.read" />}><Route path="campaigns" element={<Campaigns />} /><Route path="campaigns/new" element={<CampaignEditor />} /><Route path="campaigns/templates" element={<Templates />} /><Route path="campaigns/:id" element={<CampaignDetail />} /><Route path="campaigns/:id/edit" element={<CampaignEditor />} /></Route><Route element={<Permission name="opportunities.read" />}><Route path="opportunities" element={<Opportunities />} /><Route path="opportunities/new" element={<OpportunityEditor />} /><Route path="opportunities/:id" element={<OpportunityDetail />} /><Route path="opportunities/:id/edit" element={<OpportunityEditor />} /></Route>{(['projects', 'reports'] as const).map(module => <Route key={module} element={<Permission name={`${module}.read`} />}><Route path={module} element={<Upcoming module={module} />} /></Route>)}<Route path="settings" element={<Settings />} /><Route path="*" element={<section className="panel p-8"><h1 className="text-xl font-semibold">Page not found</h1><p className="mt-2 text-sm text-muted-foreground">Choose a module from the navigation to continue.</p></section>} /></Route></Route></Routes></Suspense></BrowserRouter><PwaControls /><Toaster position="top-right" richColors closeButton /></AuthProvider></QueryClientProvider></ErrorBoundary> }

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
