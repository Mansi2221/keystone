import { useCallback, useEffect, useState } from 'react'
import { fetchDemoUsers, fetchMe, login as apiLogin, setAuthState, clearAuthState, onTokenRefresh } from '../api'
import { isDemoMode, demoDemoUsers } from '../demo'
import type { DemoUser, Principal } from '../types'

const TOKEN_KEY = 'keystone-token'
const USER_KEY = 'keystone-user'

export function useAuth() {
  // In demo mode, ignore stale tokens from previous sessions
  const [token, setToken] = useState<string | null>(() => {
    const stored = localStorage.getItem(TOKEN_KEY)
    if (isDemoMode() && stored && !stored.startsWith('demo-token-')) return null
    return stored
  })
  const [principal, setPrincipal] = useState<Principal | null>(null)
  const [demoUsers, setDemoUsers] = useState<DemoUser[]>(isDemoMode() ? demoDemoUsers() : [])
  const [currentUserKey, setCurrentUserKey] = useState<string | null>(() => localStorage.getItem(USER_KEY))
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchDemoUsers().then(setDemoUsers).catch(() => {})
  }, [])

  // Listen for token refreshes from the api layer
  useEffect(() => {
    return onTokenRefresh((newToken) => {
      setToken(newToken)
      localStorage.setItem(TOKEN_KEY, newToken)
    })
  }, [])

  useEffect(() => {
    if (token) {
      fetchMe(token).then(setPrincipal).catch(() => {
        // Token is truly invalid — clear everything
        setToken(null)
        setPrincipal(null)
        clearAuthState()
        localStorage.removeItem(TOKEN_KEY)
      })
    }
  }, [token])

  const login = useCallback(async (username: string) => {
    setLoading(true)
    try {
      // Always get a fresh token on user switch
      const result = await apiLogin(username)
      setToken(result.token)
      setCurrentUserKey(username)
      localStorage.setItem(TOKEN_KEY, result.token)
      localStorage.setItem(USER_KEY, username)
      const me = await fetchMe(result.token)
      setPrincipal(me)
    } finally {
      setLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setPrincipal(null)
    setCurrentUserKey(null)
    clearAuthState()
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }, [])

  return {
    token,
    principal,
    demoUsers,
    currentUserKey,
    login,
    logout,
    isAuthenticated: !!token && !!principal,
    loading,
  }
}
