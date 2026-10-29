const FALLBACK = {
  not_configured: 'AI guidance is not configured. The action plan below is available.',
  disabled: 'AI guidance is turned off. The action plan below is available.',
  no_actions: 'There are no mapped actions to explain for this result.',
  busy: 'AI guidance is busy. Use the action plan below.',
  expired: 'AI guidance did not finish in time. Use the action plan below.',
}

export default function AiGuidance({ guidance, actions }) {
  if (!guidance) return null
  return (
    <section aria-label="AI recommendations" aria-live="polite" className="border rounded p-2 mb-3 small" style={{ overflowWrap: 'anywhere' }}>
      <div className="fw-semibold mb-1"><i className="bi bi-stars me-1" />AI recommendations</div>
      {guidance.status === 'pending' ? (
        <div role="status"><span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />
          Preparing AI recommendations… You can review the action plan below.
        </div>
      ) : guidance.status === 'ready' ? (
        <>
          <p className="mb-2">{guidance.summary}</p>
          {(guidance.explanations || []).map((item) => actions[item.action_index] && (
            <div key={item.action_index} className="mb-2">
              <strong>{actions[item.action_index].title}</strong>
              <div>{item.explanation}</div>
            </div>
          ))}
          <div className="text-muted">AI explanation of this forecast. Confirm pest presence through field inspection.</div>
          <div className="text-muted">The action plan uses the final risk map of the representative run. Across-run frequency is a separate view.</div>
          <div className="text-muted mt-1">{guidance.provider || 'Gemini'} · {guidance.model} · Model {guidance.simulation_model_version}</div>
        </>
      ) : (
        <div role="status" className="text-muted">{FALLBACK[guidance.reason] || 'AI guidance is unavailable. Use the action plan below.'}</div>
      )}
    </section>
  )
}
