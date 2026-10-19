import { useEffect, useState } from 'react'

export default function PasswordInput({ label = 'password', ...props }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => { if (props.disabled) setVisible(false) }, [props.disabled])
  return (
    <div className="auth-password-wrap">
      <input {...props} type={visible ? 'text' : 'password'} className="form-control" />
      <button type="button" className="auth-password-toggle" disabled={props.disabled}
        aria-label={`${visible ? 'Hide' : 'Show'} ${label}`} aria-pressed={visible} aria-controls={props.id}
        onClick={() => setVisible((value) => !value)}>
        <i className={`bi ${visible ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true" />
      </button>
    </div>
  )
}
