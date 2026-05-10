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
      <div
        className={`sidebar-section-header${open ? ' is-open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setOpen((o) => !o)}
        aria-expanded={open}
      >
        <div className="sidebar-section-icon-wrap">
          {iconName && <i className={`bi bi-${iconName} sidebar-section-icon`} />}
        </div>
        <span className="sidebar-section-title">{title}</span>
        {headerExtra && <span className="sidebar-section-extra">{headerExtra}</span>}
        <i className={`bi bi-chevron-${open ? 'up' : 'down'} sidebar-section-chevron`} />
      </div>
      {open && <div className="sidebar-section-body">{children}</div>}
    </div>
  )
}
