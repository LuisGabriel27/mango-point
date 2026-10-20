import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import api, { apiErrorMessage } from '../api'
import { getSessionApiTarget, setSessionApiTarget } from '../offline/apiRuntime'
import { SESSION_ACTIVITY_KEY, SESSION_EXPIRY_KEY, SESSION_NOTICE_KEY, SESSION_INVALID_EVENT,
  SESSION_USER_KEY, sessionValue, storeSessionValue, startSessionMonitor } from '../utils/sessionMonitor'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sessionValue(sessionStorage, 'access_token'))
  const tokenRef = useRef(token)
  const stopMonitor = useRef(null)
  const loginAttempt = useRef(0)
  const [user, setUser] = useState(() => {
    if (!token) return null
    try { return JSON.parse(sessionValue(sessionStorage, SESSION_USER_KEY)) }
    catch { return null }
  })
  const [loading, setLoading] = useState(true)
  const [sessionNotice, setSessionNotice] = useState(() => sessionValue(sessionStorage, SESSION_NOTICE_KEY) || '')

  const endSession = useCallback((message = '') => {
    // Stop listeners synchronously: a focus/visibility event can arrive before
    // React effect cleanup and must not recreate metadata after sign-out.
    stopMonitor.current?.()
    stopMonitor.current = null
    loginAttempt.current++
    tokenRef.current = null
    for (const key of ['access_token', SESSION_ACTIVITY_KEY, SESSION_EXPIRY_KEY, SESSION_USER_KEY]) storeSessionValue(sessionStorage, key, null)
    setSessionApiTarget(null)
    storeSessionValue(sessionStorage, SESSION_NOTICE_KEY, message || null)
    setSessionNotice(message)
    setToken(null)
    setUser(null)
    setLoading(false)
  }, [])

  const updateUser = useCallback((userData) => {
    storeSessionValue(sessionStorage, SESSION_USER_KEY, JSON.stringify(userData))
    setUser(userData)
  }, [])

  const applySession = useCallback((data, authTarget) => {
    if (authTarget) setSessionApiTarget(authTarget)
    tokenRef.current = data.access_token
    storeSessionValue(sessionStorage, 'access_token', data.access_token)
    const expires = Date.parse(data.expires_at)
    storeSessionValue(sessionStorage, SESSION_EXPIRY_KEY, Number.isFinite(expires) ? expires : null)
    setToken(data.access_token)
    updateUser(data.user)
  }, [updateUser])

  const login = useCallback(async (usernameOrEmail, password, options) => {
    const attempt = ++loginAttempt.current
    const res = await api.login(usernameOrEmail, password, options)
    if (attempt !== loginAttempt.current) throw new Error('Sign-in cancelled. Start again.')
    if (!res.data.verification_required || !res.data.challenge_id) {
      throw new Error('The server needs the email sign-in update. Ask the administrator to update the API.')
    }
    if (options?.recoverSessions && !res.data.session_recovery) {
      throw new Error('Session recovery needs an updated API. Ask the administrator to update MangoPoint.')
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
    applySession(res.data, res.config.authTarget)
    return res.data.user
  }, [applySession])

  const logout = useCallback(async () => {
    // Local cleanup must not wait for an unreachable server.
    const request = api.logout(tokenRef.current, getSessionApiTarget())
    endSession()
    try { await request } catch { /* Already signed out locally. */ }
  }, [endSession])

  const checkSession = useCallback(async () => {
    const previous = tokenRef.current
    try {
      const response = await api.me()
      if (previous && tokenRef.current === previous) updateUser(response.data.user ?? response.data)
    } catch (error) {
      // /auth/me rejects inactive accounts with 403; ordinary role-restricted
      // endpoint failures must not sign an otherwise valid user out.
      if (error.response?.status === 403 && previous && tokenRef.current === previous) {
        endSession(apiErrorMessage(error, 'Your account is inactive. Please sign in again.'))
      }
      throw error
    }
  }, [updateUser, endSession])

  useEffect(() => {
    const invalid = (event) => {
      if (event.detail.token === tokenRef.current) endSession(event.detail.message)
    }
    window.addEventListener(SESSION_INVALID_EVENT, invalid)
    return () => window.removeEventListener(SESSION_INVALID_EVENT, invalid)
  }, [endSession])

  useEffect(() => {
    if (!tokenRef.current) { setLoading(false); return }
    let active = true
    checkSession()
      // Network/gateway failures keep the last verified user for UI. The API's
      // authentication rejection or the local deadline still ends the session.
      .catch(() => {})
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [checkSession])

  const signedIn = Boolean(token)
  useEffect(() => {
    if (!signedIn) return
    const stop = startSessionMonitor({
      storage: sessionStorage, events: window, document, timers: window,
      onExpire: endSession,
      onCheck: checkSession,
      onRefresh: async (body) => {
        const previous = tokenRef.current
        const response = await api.refreshSession(body)
        if (previous && tokenRef.current === previous) applySession(response.data)
      },
    })
    stopMonitor.current = stop
    return () => {
      stop()
      if (stopMonitor.current === stop) stopMonitor.current = null
    }
  }, [signedIn, endSession, applySession, checkSession])

  return (
    <AuthContext.Provider value={{ token, user, loading, login, verifyLogin, resendLogin, cancelLogin, logout, updateUser, endSession, sessionNotice }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
