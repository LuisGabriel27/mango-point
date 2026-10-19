import { forwardRef, useImperativeHandle, useRef } from 'react'

const SignInCodeInput = forwardRef(function SignInCodeInput({ value, onChange, disabled, error }, ref) {
  const inputs = useRef([])
  const focus = (index) => {
    inputs.current[index]?.focus()
    inputs.current[index]?.select()
  }
  useImperativeHandle(ref, () => ({ focus: () => focus(0) }), [])

  const enterDigits = (index, text) => {
    if (disabled) return
    const digits = text.replace(/\D/g, '').slice(0, 6)
    if (!digits) { focus(index); return }
    // A full pasted/autofilled code always replaces all six positions.
    const start = digits.length === 6 ? 0 : index
    const next = [...value]
    for (let offset = 0; offset < digits.length && start + offset < 6; offset++) {
      next[start + offset] = digits[offset]
    }
    onChange(next)
    focus(Math.min(start + digits.length, 5))
  }

  const handleKeyDown = (event, index) => {
    if (disabled) return
    if (event.key === 'Backspace') {
      event.preventDefault()
      const target = value[index] || index === 0 ? index : index - 1
      const next = [...value]
      next[target] = ''
      onChange(next)
      focus(target)
    } else if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault()
      const target = event.key === 'Home' ? 0 : event.key === 'End' ? 5
        : Math.max(0, Math.min(5, index + (event.key === 'ArrowLeft' ? -1 : 1)))
      focus(target)
    }
  }

  return (
    <div className="login-code-inputs" role="group" aria-labelledby="login-code-label" dir="ltr">
      {value.map((digit, index) => (
        <input key={index} ref={(input) => { inputs.current[index] = input }}
          id={`login-code-${index + 1}`} type="text" className="form-control login-code-digit"
          aria-label={`Digit ${index + 1} of 6`}
          aria-describedby={error ? 'login-code-help login-error' : 'login-code-help'}
          inputMode="numeric" pattern="[0-9]" autoComplete={index === 0 ? 'one-time-code' : 'off'}
          // Allow browsers to supply a whole OTP; only one digit is rendered per box.
          maxLength={6} autoCapitalize="none" spellCheck={false}
          value={digit} required autoFocus={index === 0} disabled={disabled}
          onFocus={(event) => event.currentTarget.select()}
          onChange={(event) => {
            if (event.target.value === '') {
              const next = [...value]
              next[index] = ''
              onChange(next)
            } else enterDigits(index, event.nativeEvent.data ?? event.target.value)
          }}
          onPaste={(event) => { event.preventDefault(); enterDigits(index, event.clipboardData.getData('text')) }}
          onKeyDown={(event) => handleKeyDown(event, index)}
        />
      ))}
    </div>
  )
})

export default SignInCodeInput
