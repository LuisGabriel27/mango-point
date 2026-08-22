import { useState, useEffect } from 'react'

export default function CollapsibleCard({
  iconName,
  title,
  children,
  headerExtra = null,
  defaultOpen = true,
  openOverride = 0,
  cardClass = '',
  cardStyle = {},
  embedded = false,
}) {
  const [open, setOpen] = useState(defaultOpen)

  useEffect(() => {
    if (openOverride > 0) setOpen(true)
  }, [openOverride])

  if (embedded) {
    return (
      <section className={`sidebar-section sidebar-section-embedded ${cardClass}`} style={cardStyle}>
        <div className="sidebar-section-heading">
          <div className="sidebar-section-icon-wrap is-static">
            {iconName && <i className={`bi bi-${iconName} sidebar-section-icon`} />}
          </div>
          <span className="sidebar-section-title">{title}</span>
          {headerExtra && <span className="sidebar-section-extra">{headerExtra}</span>}
        </div>
        <div className="sidebar-section-body">{children}</div>
      </section>
    )
  }

  return (
    <div className={`sidebar-section ${cardClass}`} style={cardStyle}>
      <button
        type="button"
        className={`sidebar-section-header${open ? ' is-open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <div className="sidebar-section-icon-wrap">
          {iconName && <i className={`bi bi-${iconName} sidebar-section-icon`} />}
        </div>
        <span className="sidebar-section-title">{title}</span>
        {headerExtra && <span className="sidebar-section-extra">{headerExtra}</span>}
        <i className={`bi bi-chevron-${open ? 'up' : 'down'} sidebar-section-chevron`} />
      </button>
      {open && <div className="sidebar-section-body">{children}</div>}
    </div>
  )
}
