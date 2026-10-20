import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, send } from '@/lib/api'
import type { User } from '@/types'

type Auth = { user: User | null | undefined; loading: boolean; error: Error | null; can: (permission: string) => boolean; setUser: (user: User | null) => void; logout: () => Promise<void>; retry: () => void; recoveryCodes: string[]; setRecoveryCodes: (codes: string[]) => void }
const Context = createContext<Auth | null>(null)
export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const query = useQuery({ queryKey: ['me'], queryFn: async () => { try { return await api<User>('/auth/me') } catch (error) { if (error instanceof ApiError && error.status === 401) return null; throw error } }, retry: false, staleTime: 30_000 })
  const setUser = (user: User | null) => { client.removeQueries({ predicate: query => query.queryKey[0] !== 'me' }); client.setQueryData(['me'], user) }
  useEffect(() => { const expired = () => { setRecoveryCodes([]); client.removeQueries({ predicate: query => query.queryKey[0] !== 'me' }); client.setQueryData(['me'], null) }; window.addEventListener('session-expired', expired); return () => window.removeEventListener('session-expired', expired) }, [client])
  return <Context.Provider value={{ user: query.data, loading: query.isPending, error: query.error, can: p => query.data?.permissions.includes(p) ?? false, setUser,
    logout: async () => { await send('/auth/logout'); setRecoveryCodes([]); setUser(null) }, retry: () => { void query.refetch() }, recoveryCodes, setRecoveryCodes }}>{children}</Context.Provider>
}
export function useAuth() { const auth = useContext(Context); if (!auth) throw new Error('Missing authentication provider'); return auth }
