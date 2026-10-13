import { useEffect, useRef } from 'react'

export default function LoginTerms() {
  const dialogRef = useRef(null)
  const previousOverflow = useRef(null)

  const restoreScroll = () => {
    if (previousOverflow.current !== null) {
      document.body.style.overflow = previousOverflow.current
      previousOverflow.current = null
    }
  }

  useEffect(() => {
    const dialog = dialogRef.current
    return () => {
      if (dialog.open) dialog.close()
      restoreScroll()
    }
  }, [])

  const openTerms = () => {
    if (dialogRef.current.open) return
    dialogRef.current.showModal()
    previousOverflow.current = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }

  const closeTerms = () => dialogRef.current.close()

  const handleKeyDown = (event) => {
    if (event.key !== 'Tab') return
    const controls = dialogRef.current.querySelectorAll('button, [tabindex="0"]')
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <>
      <p className="login-terms-notice">
        By signing in, you agree to our{' '}
        <button type="button" className="auth-inline-link login-terms-link" onClick={openTerms} aria-haspopup="dialog">
          Terms and Conditions
        </button>.
      </p>

      <dialog ref={dialogRef} className="login-terms-dialog" aria-labelledby="login-terms-title" aria-describedby="login-terms-intro" onClose={restoreScroll} onKeyDown={handleKeyDown}>
        <header className="login-terms-header">
          <h2 id="login-terms-title">Terms and Conditions</h2>
          <button type="button" className="btn-close" aria-label="Close terms and conditions" onClick={closeTerms} />
        </header>
        <div className="login-terms-body" tabIndex={0}>
          <p id="login-terms-intro">Please read these terms before using MangoPoint.</p>
          <h3>Authorized use</h3>
          <p>Use MangoPoint only with an authorized account and for orchard monitoring, planning, and record keeping. Do not attempt to access accounts or orchard records without permission, or disrupt the service.</p>
          <h3>Account security</h3>
          <p>Keep your login details private and sign out on shared devices. Report suspected unauthorized access to your administrator.</p>
          <h3>Orchard records and sharing</h3>
          <p>Enter records you are authorized to provide and check their accuracy. Keep field observations separate from simulated outcomes. Share reports and orchard information only with people authorized to receive them.</p>
          <h3>Forecast limitations</h3>
          <p>Simulations, risk maps, alerts, and crop-impact estimates depend on the selected inputs, weather, and model assumptions. They are modeled estimates, not confirmed field infestations or guarantees of forecast accuracy, yield, or financial benefit.</p>
          <h3>Farm decisions</h3>
          <p>Use MangoPoint alongside actual orchard inspections and qualified agricultural advice. Treatment scenarios are not pesticide product or dosage recommendations. You are responsible for checking conditions before taking farm actions.</p>
          <h3>Service availability</h3>
          <p>Access, weather data, and notifications may be delayed or unavailable. Review data dates and sources, and keep copies of records you need for farm operations.</p>
        </div>
        <footer className="login-terms-footer">
          <button type="button" className="btn btn-success" onClick={closeTerms}>Close</button>
        </footer>
      </dialog>
    </>
  )
}
