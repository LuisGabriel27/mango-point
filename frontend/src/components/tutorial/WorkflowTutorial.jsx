import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ACTIONS, EVENTS, Joyride } from 'react-joyride'
import { buildTutorialSteps, readTutorialPreference, rememberTutorial, tutorialPreferenceKey } from './tutorialSteps'
import './tutorial.css'

function TutorialTooltip({ index, size, step, backProps, closeProps, primaryProps, skipProps, tooltipProps }) {
  const phases = [
    ['setup', 'Setup'], ['simulate', 'Simulate'], ['results', 'Results'],
    ['history', 'History'], ['verify', 'Verify'], ['settings', 'Settings'],
  ]
  return (
    <section {...tooltipProps} className="workflow-tour-tooltip" aria-labelledby="workflow-tour-title" aria-describedby="workflow-tour-content">
      <div className="workflow-tour-topline">
        <span aria-live="polite">Step {index + 1} of {size}</span>
        <button {...closeProps} type="button" className="workflow-tour-close" aria-label="Close tutorial">×</button>
      </div>
      <div className="workflow-tour-flow" aria-label="MangoPoint workflow">
        {phases.map(([id, label]) => (
          <span key={id} className={step.data?.phase === id ? 'is-current' : ''}>{label}</span>
        ))}
      </div>
      <h2 id="workflow-tour-title">{step.title}</h2>
      <div id="workflow-tour-content" className="workflow-tour-explanation">
        <strong>{['welcome', 'finish'].includes(step.id) ? 'How it works' : 'What to do'}</strong>
        <p>{step.content}</p>
        {step.data?.tip && (
          <aside>
            <i className="bi bi-lightbulb" aria-hidden="true" />
            <span><strong>Why it matters</strong>{step.data.tip}</span>
          </aside>
        )}
      </div>
      <div className="workflow-tour-actions">
        <button {...skipProps} type="button" className="btn btn-sm btn-link">Skip tutorial</button>
        <div>
          {index > 0 && <button {...backProps} type="button" className="btn btn-sm btn-outline-secondary">Back</button>}
          <button {...primaryProps} type="button" className="btn btn-sm btn-success">{index + 1 === size ? 'Finish' : 'Next'}</button>
        </div>
      </div>
    </section>
  )
}

function RunningTutorial({ definitions, presentation, onPresentationChange, onEnd, onMissing }) {
  const pending = useRef(null)
  const alive = useRef(true)
  const [compactViewport, setCompactViewport] = useState(() => (
    typeof window !== 'undefined' && window.matchMedia('(max-width: 600px)').matches
  ))
  const prepare = useCallback((view) => new Promise((resolve) => {
    if (!alive.current) { resolve(); return }
    pending.current?.()
    pending.current = resolve
    onPresentationChange({ ...view })
  }), [onPresentationChange])
  // Resolve readiness after React commits the tab/panel override. Joyride then
  // waits for the target itself; no timers or externally controlled step index.
  useLayoutEffect(() => {
    pending.current?.()
    pending.current = null
  }, [presentation])
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false; pending.current?.(); pending.current = null }
  }, [])
  useEffect(() => {
    const media = window.matchMedia('(max-width: 600px)')
    const update = () => setCompactViewport(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      onEnd()
    }
    document.addEventListener('keydown', closeOnEscape, true)
    return () => document.removeEventListener('keydown', closeOnEscape, true)
  }, [onEnd])
  const steps = useMemo(() => definitions.map((step) => ({
    ...step,
    placement: compactViewport ? 'center' : step.placement,
    before: () => prepare(step.data.view),
  })), [compactViewport, definitions, prepare])

  return <Joyride run continuous scrollToFirstStep steps={steps}
    tooltipComponent={TutorialTooltip}
    options={{
      skipBeacon: true, showProgress: true, buttons: ['back', 'close', 'primary', 'skip'],
      closeButtonAction: 'skip', dismissKeyAction: false, overlayClickAction: false,
      blockTargetInteraction: true, targetWaitTimeout: 1600, beforeTimeout: 3000,
      overlayColor: 'rgba(70, 76, 82, 0.72)', primaryColor: '#237547',
      spotlightPadding: 6, spotlightRadius: 8, zIndex: 20000,
      width: 'min(370px, calc(100vw - 24px))', scrollDuration: 0, scrollOffset: 16,
    }}
    locale={{ back: 'Back', close: 'Close tutorial', last: 'Finish', next: 'Next', skip: 'Skip tutorial' }}
    onEvent={({ type, action }) => {
      if (type === EVENTS.TARGET_NOT_FOUND) onMissing()
      if (type === EVENTS.ERROR) onEnd('A tutorial panel was unavailable. You can replay the guide when it is ready.')
      else if (type === EVENTS.TOUR_END || action === ACTIONS.CLOSE) onEnd()
    }}
  />
}

export default function WorkflowTutorial({ user, orchardId, customWeather, hasResult, hasPlayback,
  hasRepeatedRuns, presentation, onPresentationChange }) {
  const key = tutorialPreferenceKey(user)
  const [invited, setInvited] = useState(() => !readTutorialPreference(key))
  const [menuOpen, setMenuOpen] = useState(false)
  const [session, setSession] = useState(null)
  const [notice, setNotice] = useState('')
  const launcher = useRef(null)
  const menu = useRef(null)
  const restore = useRef(null)
  const restoreLauncherFocus = useRef(false)
  const missed = useRef(false)
  const active = useRef(false)

  useEffect(() => { setInvited(!readTutorialPreference(key)) }, [key])
  const end = useCallback((message = '') => {
    if (!active.current) return
    active.current = false
    restoreLauncherFocus.current = true
    setSession(null)
    onPresentationChange(null)
    setNotice(message || (missed.current ? 'Unavailable controls were skipped. Replay the guide after loading the relevant weather or result.' : 'Tutorial closed. Your inputs are unchanged; replay anytime.'))
    const savedScroll = restore.current
    restore.current = null
    requestAnimationFrame(() => {
      savedScroll?.forEach(({ element, top, left }) => {
        if (element.isConnected) element.scrollTo({ top, left, behavior: 'instant' })
      })
    })
  }, [onPresentationChange])

  useEffect(() => {
    if (session || !restoreLauncherFocus.current) return
    restoreLauncherFocus.current = false
    launcher.current?.focus({ preventScroll: true })
  }, [session])

  useEffect(() => {
    if (session && (session.orchardId !== orchardId || session.userKey !== key)) {
      end('The orchard or signed-in user changed. Restart Tutorial for the current orchard.')
    }
  }, [orchardId, key, session, end])
  useEffect(() => () => { onPresentationChange(null) }, [onPresentationChange])

  useEffect(() => {
    if (!menuOpen) return undefined
    menu.current?.querySelector('button')?.focus()
    const dismiss = (event) => {
      if (!menu.current?.contains(event.target) && !launcher.current?.contains(event.target)) setMenuOpen(false)
    }
    document.addEventListener('pointerdown', dismiss)
    return () => document.removeEventListener('pointerdown', dismiss)
  }, [menuOpen])

  const start = (guide) => {
    if (document.querySelector('[aria-modal="true"], .modal.show, .weather-periods-modal')) {
      setNotice('Close the open dialog first, then start Tutorial. Your unfinished inputs will stay in place.')
      setMenuOpen(false)
      return
    }
    rememberTutorial(key)
    setInvited(false)
    setMenuOpen(false)
    setNotice('')
    missed.current = false
    active.current = true
    restore.current = [...document.querySelectorAll('[data-tour-scroll]')].map((element) => ({
      element, top: element.scrollTop, left: element.scrollLeft,
    }))
    onPresentationChange({ tab: 'live-map' })
    setSession({ orchardId, userKey: key, steps: buildTutorialSteps({ guide, customWeather,
      hasResult, hasPlayback, hasRepeatedRuns,
      isAdmin: String(user?.role || '').toLowerCase() === 'admin' }) })
  }

  return <div className="workflow-tour-entry">
    <button type="button" className="navbar-controls-btn workflow-tour-launcher" data-tour="tutorial-start"
      ref={launcher} aria-expanded={menuOpen} aria-controls="workflow-tour-menu"
      onClick={() => setMenuOpen((open) => !open)}>
      <i className="bi bi-question-circle" aria-hidden="true" /><span>Tutorial</span>
    </button>
    {!session && (menuOpen || invited) && <div className="workflow-tour-menu" id="workflow-tour-menu" ref={menu}
      onKeyDown={(event) => { if (event.key === 'Escape') {
        event.stopPropagation(); setMenuOpen(false); setInvited(false); rememberTutorial(key); launcher.current?.focus()
      } }}>
      <strong>New to MangoPoint?</strong>
      <p>Start with the short overview. Then use a pest guide when you are ready to prepare a forecast. The guides point to controls but never change or submit them.</p>
      <button type="button" className="btn btn-success btn-sm workflow-tour-choice" onClick={() => start('workflow')}>
        <i className="bi bi-signpost-split" aria-hidden="true" /><span><strong>Quick start</strong><small>Learn the workflow, account settings and alerts</small></span>
      </button>
      <button type="button" className="btn btn-outline-success btn-sm workflow-tour-choice" onClick={() => start('cecid')}>
        <i className="bi bi-droplet" aria-hidden="true" /><span><strong>Cecid Fly setup</strong><small>Fruitlets, source, soil, rain, light and wind</small></span>
      </button>
      <button type="button" className="btn btn-outline-success btn-sm workflow-tour-choice" onClick={() => start('fruitfly')}>
        <i className="bi bi-bug" aria-hidden="true" /><span><strong>Fruit Fly setup</strong><small>Mature fruit, adult source, warmth and daylight</small></span>
      </button>
      <button type="button" className="btn btn-outline-success btn-sm workflow-tour-choice" onClick={() => start('results')}>
        <i className="bi bi-graph-up-arrow" aria-hidden="true" /><span><strong>Understand results</strong><small>Map, playback, History and field checking</small></span>
      </button>
      <button type="button" className="btn btn-link btn-sm" onClick={() => {
        rememberTutorial(key); setInvited(false); setMenuOpen(false); launcher.current?.focus()
      }}>{invited ? 'Maybe later' : 'Close menu'}</button>
    </div>}
    {notice && !session && <div className="workflow-tour-notice" role="status">{notice}
      <button type="button" aria-label="Dismiss tutorial message" onClick={() => setNotice('')}>×</button>
    </div>}
    {session && <RunningTutorial definitions={session.steps} presentation={presentation}
      onPresentationChange={onPresentationChange} onEnd={end} onMissing={() => { missed.current = true }} />}
  </div>
}
