import { useState } from 'react'

export default function CollapsibleCard({
  iconName,
  title,
  children,
  headerExtra = null,
  defaultOpen = true,
  cardClass = '',
  cardStyle = {},
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={`sidebar-section ${cardClass}`} style={cardStyle}>
      <div className="sidebar-section-header" onClick={() => setOpen((o) => !o)}>
        {iconName && <i className={`bi bi-${iconName} sidebar-section-icon`} />}
        <span className="sidebar-section-title">{title}</span>
        {headerExtra && <span className="sidebar-section-extra">{headerExtra}</span>}
        <button
          type="button"
          className="sidebar-section-toggle"
          onClick={(e) => { e.stopPropagation(); setOpen((o) => !o) }}
          aria-label={open ? 'Collapse' : 'Expand'}
        >
          {open ? '−' : '+'}
        </button>
      </div>
      {open && <div className="sidebar-section-body">{children}</div>}
    </div>
  )
}
