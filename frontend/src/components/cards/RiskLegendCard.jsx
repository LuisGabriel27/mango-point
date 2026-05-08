import CollapsibleCard from '../CollapsibleCard'

const RISK_ITEMS = [
  ['< 15 %', '#ffffb2'],
  ['15-30 %', '#fecc5c'],
  ['30-50 %', '#fd8d3c'],
  ['50-70 %', '#f03b20'],
  ['70-85 %', '#e31a1c'],
  ['85-90 %', '#bd0026'],
  ['90-100 %', '#800026'],
]

const STATE_ITEMS = [
  ['Healthy', '#22c55e'],
  ['Infected', '#ef4444'],
  ['Bagged', '#3b82f6'],
  ['Dead', '#424242'],
]

function Swatch({ color, label, circle }) {
  return (
    <div className="mb-1">
      <span style={{
        display: 'inline-block', width: 14, height: 14,
        backgroundColor: color, marginRight: 6, verticalAlign: 'middle',
        border: '1px solid #aaa', borderRadius: circle ? '50%' : '2px',
      }} />
      <span style={{ fontSize: '.8rem' }}>{label}</span>
    </div>
  )
}

export default function RiskLegendCard() {
  return (
    <CollapsibleCard iconName="info-circle" title="Legend">
      <small className="d-block mb-1">
        <i className="bi bi-palette me-1" /><strong>Risk Scale</strong>
      </small>
      {RISK_ITEMS.map(([l, c]) => <Swatch key={l} label={l} color={c} />)}
      <hr className="my-2" />
      <small className="d-block mb-1">
        <i className="bi bi-tree me-1" /><strong>Tree States</strong>
      </small>
      {STATE_ITEMS.map(([l, c]) => <Swatch key={l} label={l} color={c} circle />)}
    </CollapsibleCard>
  )
}
