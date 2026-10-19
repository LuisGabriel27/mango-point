import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import api from '../api'
import { SESSION_ACTIVITY_KEY, SESSION_EXPIRY_KEY, SESSION_NOTICE_KEY, SESSION_INVALID_EVENT,
  sessionValue, storeSessionValue, startSessionMonitor } from '../utils/sessionMonitor'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sessionValue(sessionStorage, 'access_token'))
  const tokenRef = useRef(token)
  const loginAttempt = useRef(0)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sessionNotice, setSessionNotice] = useState(() => sessionValue(sessionStorage, SESSION_NOTICE_KEY) || '')

  const endSession = useCallback((message = '') => {
    loginAttempt.current++
    tokenRef.current = null
    for (const key of ['access_token', SESSION_ACTIVITY_KEY, SESSION_EXPIRY_KEY]) storeSessionValue(sessionStorage, key, null)
    storeSessionValue(sessionStorage, SESSION_NOTICE_KEY, message || null)
    setSessionNotice(message)
    setToken(null)
    setUser(null)
    setLoading(false)
  }, [])

  const applySession = useCallback((data) => {
    tokenRef.current = data.access_token
    storeSessionValue(sessionStorage, 'access_token', data.access_token)
    const expires = Date.parse(data.expires_at)
    storeSessionValue(sessionStorage, SESSION_EXPIRY_KEY, Number.isFinite(expires) ? expires : null)
    setToken(data.access_token)
    setUser(data.user)
  }, [])

  const login = useCallback(async (usernameOrEmail, password) => {
    const attempt = ++loginAttempt.current
    const res = await api.login(usernameOrEmail, password)
    if (attempt !== loginAttempt.current) throw new Error('Sign-in cancelled. Start again.')
    if (!res.data.verification_required || !res.data.challenge_id) {
      throw new Error('The server needs the email sign-in update. Ask the administrator to update the API.')
    }
    return { ...res.data, authTarget: res.config.authTarget, attempt }
  }, [])

  const cancelLogin = useCallback(() => { loginAttempt.current++ }, [])

  const resendLogin = useCallback(async (challenge) => {
    if (challenge.attempt !== loginAttempt.current) throw new Error('Sign-in cancelled. Start again.')
    const res = await api.resendLogin({ challenge_id: challenge.challenge_id }, challenge.authTarget)
    if (challenge.attempt !== loginAttempt.current) throw new Error('Sign-in cancelled. Start again.')
    return { ...res.data, authTarget: challenge.authTarget, attempt: challenge.attempt }
  }, [])

  const verifyLogin = useCallback(async (challenge, code) => {
    if (challenge.attempt !== loginAttempt.current) throw new Error('Sign-in cancelled. Start again.')
    const res = await api.verifyLogin({ challenge_id: challenge.challenge_id, code }, challenge.authTarget)
    if (challenge.attempt !== loginAttempt.current) throw new Error('Sign-in cancelled. Start again.')
    storeSessionValue(sessionStorage, SESSION_ACTIVITY_KEY, Date.now())
    storeSessionValue(sessionStorage, SESSION_NOTICE_KEY, null)
    setSessionNotice('')
    applySession(res.data)
    return res.data.user
  }, [applySession])

  const logout = useCallback(async () => {
    // Local cleanup must not wait for an unreachable server.
    const request = api.logout(tokenRef.current)
    endSession()
    try { await request } catch { /* Already signed out locally. */ }
  }, [endSession])

  const updateUser = useCallback((userData) => {
    setUser(userData)
  }, [])

  useEffect(() => {
    const invalid = (event) => {
      if (event.detail.token === tokenRef.current) endSession(event.detail.message)
    }
    window.addEventListener(SESSION_INVALID_EVENT, invalid)
    return () => window.removeEventListener(SESSION_INVALID_EVENT, invalid)
  }, [endSession])

  useEffect(() => {
    const restoredToken = tokenRef.current
    if (!restoredToken) { setLoading(false); return }
    api.me()
      .then((res) => { if (tokenRef.current === restoredToken) setUser(res.data.user ?? res.data) })
      .catch(() => {
        if (tokenRef.current === restoredToken) endSession('Please sign in again to restore your session.')
      })
      .finally(() => setLoading(false))
  }, [endSession])

  const signedIn = Boolean(token)
  useEffect(() => {
    if (!signedIn) return
    return startSessionMonitor({
      storage: sessionStorage, events: window, document, timers: window,
      onExpire: endSession,
      onCheck: () => api.me(),
      onRefresh: async (body) => {
        const previous = tokenRef.current
        const response = await api.refreshSession(body)
        if (previous && tokenRef.current === previous) applySession(response.data)
      },
    })
  }, [signedIn, endSession, applySession])

  return (
    <AuthContext.Provider value={{ token, user, loading, login, verifyLogin, resendLogin, cancelLogin, logout, updateUser, endSession, sessionNotice }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
