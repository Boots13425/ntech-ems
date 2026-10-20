import { Link } from 'react-router-dom'
import { ArrowLeft, ChartNoAxesCombined, FolderKanban, Mail, Target } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState, PageHeader } from '@/components/shared'

const modules = {
  campaigns: { title: 'Email campaigns', icon: Mail, description: 'Personal outreach, reusable templates, and thoughtful follow-ups.', next: 'Campaign drafts, approvals, provider integration, reply synchronization, and controlled follow-ups are planned for the outreach phase.' },
  opportunities: { title: 'Opportunities', icon: Target, description: 'Connect customer needs with partners and commercial outcomes.', next: 'Configurable sales stages, partner matching, commercial values, and next actions are planned for the pipeline phase.' },
  projects: { title: 'Projects', icon: FolderKanban, description: 'Keep your delivery teams, milestones, and commitments connected.', next: 'Projects, assignments, milestones, and delivery tracking are planned for the operations phase.' },
  reports: { title: 'Reports', icon: ChartNoAxesCombined, description: 'Understand business performance using verified operational records.', next: 'Financial reporting, advanced analysis, and CSV, Excel, and PDF exports are planned for the analytics phase. Current relationship counts are available on Overview.' },
}
export default function UpcomingPage({ module }: { module: keyof typeof modules }) { const item = modules[module]; return <><PageHeader eyebrow="Operations workspace" title={item.title} description={item.description} /><section className="panel"><div className="flex justify-center pt-10"><Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">Upcoming module</Badge></div><EmptyState icon={item.icon} title={`${item.title} will be available in a later phase`} description={item.next} action={<Button asChild variant="outline"><Link to="/"><ArrowLeft className="size-4" />Back to overview</Link></Button>} /></section></> }
