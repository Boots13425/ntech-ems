import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { LoaderCircle } from 'lucide-react'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { api, ApiError, send } from '@/lib/api'
import { useAuth } from '@/features/auth/auth-context'
import type { Classification, Organization, Page, User } from '@/types'

const schema = z.object({
  name: z.string().trim().min(2, 'Enter at least two characters').max(180),
  industry: z.string().max(100), country: z.string().trim().min(2, 'Enter a country').max(100), city: z.string().max(100),
  email: z.union([z.email('Enter a valid email address'), z.literal('')]), phone: z.string().max(40),
  website: z.union([z.url({ protocol: /^https?$/ }), z.literal('')]), address: z.string().max(500), notes: z.string().max(10000),
  classifications: z.array(z.enum(['prospect', 'customer', 'partner', 'supplier'])).min(1, 'Choose at least one classification'), owner_id: z.string(),
})
type Values = z.infer<typeof schema>
export function OrganizationForm({ organization, classification, onClose, onSaved }: { organization?: Organization; classification?: Classification; onClose: () => void; onSaved?: (org: Organization) => void }) {
  const auth = useAuth()
  const client = useQueryClient()
  const staff = useQuery({ queryKey: ['staff-owners'], queryFn: () => api<Page<User>>('/staff?page_size=100'), enabled: auth.can('staff.read') && auth.can('organizations.all') })
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: {
    name: organization?.name || '', industry: organization?.industry || '', country: organization?.country || 'Cameroon', city: organization?.city || '',
    email: organization?.email || '', phone: organization?.phone || '', website: organization?.website || '', address: organization?.address || '', notes: organization?.notes || '',
    classifications: organization?.classifications || [classification || 'prospect'], owner_id: organization?.owner_id || auth.user!.id,
  } })
  const mutation = useMutation({ mutationFn: (values: Values) => {
    const payload = { ...values, industry: values.industry || null, city: values.city || null, email: values.email || null, phone: values.phone || null, website: values.website || null, address: values.address || null, notes: values.notes || null }
    return send<Organization>(organization ? `/organizations/${organization.id}` : '/organizations', payload, organization ? 'PUT' : 'POST')
  }, onSuccess: org => { void client.invalidateQueries({ queryKey: ['organizations'] }); void client.invalidateQueries({ queryKey: ['organization', org.id] }); void client.invalidateQueries({ queryKey: ['activity', org.id] }); void client.invalidateQueries({ queryKey: ['dashboard'] }); void client.invalidateQueries({ queryKey: ['organization-filters'] }); toast.success(organization ? 'Organization updated' : 'Organization created'); onSaved?.(org); onClose() },
  onError: error => { if (error instanceof ApiError) error.errors?.forEach(e => form.setError(e.field as keyof Values, { message: e.message })); form.setError('root', { message: error.message }) } })
  function field(name: Exclude<keyof Values, 'classifications' | 'notes' | 'owner_id'>, label: string, type = 'text', placeholder?: string) { return <div><label htmlFor={`org-${name}`} className="field-label">{label}</label><Input id={`org-${name}`} type={type} placeholder={placeholder} {...form.register(name)} aria-invalid={!!form.formState.errors[name]} />{form.formState.errors[name] && <p className="mt-1 text-xs text-destructive">{form.formState.errors[name]?.message}</p>}</div> }
  return <Dialog open onOpenChange={open => { if (!open && !mutation.isPending) onClose() }}><DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl"><DialogHeader><DialogTitle>{organization ? 'Edit organization' : 'Add an organization'}</DialogTitle><DialogDescription>Keep a shared, accurate record of your business relationship.</DialogDescription></DialogHeader><form onSubmit={form.handleSubmit(values => mutation.mutate(values))} className="mt-3 space-y-5"><div className="grid gap-4 sm:grid-cols-2"><div className="sm:col-span-2">{field('name', 'Organization name *', 'text', 'Full organization name')}</div>{field('industry', 'Industry', 'text', 'e.g. Technology')}{field('country', 'Country *')}{field('city', 'City')}{field('website', 'Website', 'url', 'https://')}{field('email', 'General email', 'email')}{field('phone', 'Phone', 'tel')}<div className="sm:col-span-2">{field('address', 'Address')}</div></div>
  <fieldset><legend className="field-label">Relationship classifications *</legend><p className="mb-3 text-xs text-muted-foreground">An organization can have more than one relationship with ETS-NTECH.</p><div className="flex flex-wrap gap-3">{(['prospect', 'customer', 'partner', 'supplier'] as Classification[]).map(value => <label key={value} className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-xs capitalize"><input type="checkbox" value={value} {...form.register('classifications')} className="size-4 accent-primary" />{value}</label>)}</div>{form.formState.errors.classifications && <p className="mt-2 text-xs text-destructive">{form.formState.errors.classifications.message}</p>}</fieldset>
  {staff.data && <div><label htmlFor="org-owner" className="field-label">Relationship owner</label><select id="org-owner" className="select-input" {...form.register('owner_id')}>{staff.data.items.filter(u => u.is_active).map(u => <option key={u.id} value={u.id}>{u.full_name}{u.id === auth.user!.id ? ' (you)' : ''}</option>)}</select></div>}
  <div><label htmlFor="org-notes" className="field-label">Relationship notes</label><Textarea id="org-notes" rows={3} placeholder="Useful context for your team…" {...form.register('notes')} /></div>{form.formState.errors.root && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-destructive">{form.formState.errors.root.message}</p>}<div className="flex justify-end gap-3 border-t pt-4"><Button type="button" variant="outline" onClick={onClose} disabled={mutation.isPending}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending && <LoaderCircle className="size-4 animate-spin" />}{organization ? 'Save changes' : 'Create organization'}</Button></div></form></DialogContent></Dialog>
}
