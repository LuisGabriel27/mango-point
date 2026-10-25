export default function AuthLayout({ eyebrow, title, description, children, footer, compact = false }) {
  return (
    <div className={`auth-shell${compact ? ' auth-shell-compact' : ''}`}>
      <main className="login-shell login-grid">
          <section className="login-hero-panel" aria-label="About MangoPoint">
            <div className="login-brand">
              <div className="login-brand-lockup">
                <img src="/brand/mangopoint-logo-v3.png" alt="" aria-hidden="true" className="login-logo" width="48" height="48" />
                <span className="login-brand-name">MangoPoint</span>
              </div>
            </div>

            <div className="login-hero-content">
              <div className="login-photo-collage" role="img" aria-label="Aerial views of a mango orchard">
                <img className="login-photo login-photo-main" src="/brand/login-orchard-canopy.jpg" alt="" width="4000" height="2250" loading="lazy" decoding="async" />
                <img className="login-photo login-photo-river" src="/brand/login-orchard-river.jpg" alt="" width="4000" height="2250" loading="lazy" decoding="async" />
                <img className="login-photo login-photo-trees" src="/brand/login-orchard-trees.jpg" alt="" width="4000" height="2250" loading="lazy" decoding="async" />
              </div>
              <h2 className="login-hero-heading">A clearer view of<br />your orchard.</h2>
              <p className="login-hero-copy">
                Bring tree health, pest forecasts, and orchard records together in one workspace.
              </p>
              <ul className="login-feature-list">
                <li className="login-feature">
                  <span className="login-feature-icon"><i className="bi bi-map" aria-hidden="true" /></span>
                  <div><h3>Monitor your orchard</h3><p>View tree health and zones on your live map.</p></div>
                </li>
                <li className="login-feature">
                  <span className="login-feature-icon"><i className="bi bi-graph-up-arrow" aria-hidden="true" /></span>
                  <div><h3>Plan your next steps</h3><p>Explore pest forecasts and recommendations.</p></div>
                </li>
                <li className="login-feature">
                  <span className="login-feature-icon"><i className="bi bi-file-earmark-text" aria-hidden="true" /></span>
                  <div><h3>Keep a clear record</h3><p>Review past simulations and print your reports.</p></div>
                </li>
              </ul>
            </div>
          </section>

          <section className="login-card" aria-labelledby="auth-title">
            <div className="login-card-body">
              <header className="login-card-header">
                <div className="login-card-kicker"><i className="bi bi-shield-lock" aria-hidden="true" />{eyebrow}</div>
                <h1 id="auth-title" className="login-card-title">{title}</h1>
                <p className="login-card-copy">{description}</p>
              </header>
              {children}
              {footer && <div className="login-card-footer">{footer}</div>}
            </div>
          </section>
        <footer className="login-page-footer">MangoPoint <span aria-hidden="true">&middot;</span> Supporting informed orchard decisions</footer>
      </main>
    </div>
  )
}
