import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sessionStorage.getItem('access_token'))
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const login = useCallback(async (usernameOrEmail, password) => {
    const res = await api.login(usernameOrEmail, password)
    const { access_token, user: userData } = res.data
    sessionStorage.setItem('access_token', access_token)
    setToken(access_token)
    setUser(userData)
    return userData
  }, [])

  const logout = useCallback(async () => {
    try { await api.logout() } catch (_) { /* swallow */ }
    sessionStorage.removeItem('access_token')
    setToken(null)
    setUser(null)
  }, [])

  useEffect(() => {
    if (!token) { setLoading(false); return }
    api.me()
      .then((res) => setUser(res.data.user ?? res.data))
      .catch(() => {
        sessionStorage.removeItem('access_token')
        setToken(null)
      })
      .finally(() => setLoading(false))
  }, [token])

  return (
    <AuthContext.Provider value={{ token, user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
