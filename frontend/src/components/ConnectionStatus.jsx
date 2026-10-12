import { useEffect, useState } from 'react'
import {
  getConnectionState,
  resolveApiTarget,
  subscribeConnectionState,
} from '../offline/apiRuntime'

const DISMISSED_STATUS_KEY = 'mangopoint.connection-status.dismissed'

function connectionSignature(connection) {
  return `${connection.mode}:${connection.internetAvailable ? 'online' : 'offline'}`
}

function dismissedSignature() {
  try {
    return window.sessionStorage.getItem(DISMISSED_STATUS_KEY)
  } catch {
    return null
  }
}

export default function ConnectionStatus() {
  const [connection, setConnection] = useState(getConnectionState)
  const [dismissed, setDismissed] = useState(dismissedSignature)

  useEffect(() => {
    const unsubscribe = subscribeConnectionState(setConnection)
    resolveApiTarget().catch(() => {})
    return unsubscribe
  }, [])

  if (connection.mode === 'checking' || (connection.mode === 'remote' && connection.internetAvailable)) {
    return null
  }

  const signature = connectionSignature(connection)
  if (dismissed === signature) return null

  const dismiss = () => {
    try {
      window.sessionStorage.setItem(DISMISSED_STATUS_KEY, signature)
    } catch {
      // The close button should still work when browser storage is unavailable.
    }
    setDismissed(signature)
  }

  const localReady = connection.mode === 'local'
  return (
    <div
      className={`connection-status ${localReady ? 'connection-status-local' : 'connection-status-error'}`}
      role="status"
      aria-live="polite"
    >
      <i className={`bi ${localReady ? 'bi-hdd-network' : 'bi-exclamation-triangle'}`} aria-hidden="true" />
      <span>
        {localReady
          ? connection.internetAvailable
            ? 'Local-first mode: simulations and records use this device.'
            : 'Offline local-first mode: simulations save locally; cloud backup resumes after reconnection.'
          : 'Offline companion unavailable. Start MangoPoint Docker, then retry.'}
      </span>
      {!localReady && (
        <button
          type="button"
          className="connection-status-retry"
          onClick={() => resolveApiTarget({ forceProbe: true })}
        >
          Retry
        </button>
      )}
      <button
        type="button"
        className="connection-status-close"
        aria-label="Close connection status"
        title="Close"
        onClick={dismiss}
      >
        <i className="bi bi-x-lg" aria-hidden="true" />
      </button>
    </div>
  )
}
