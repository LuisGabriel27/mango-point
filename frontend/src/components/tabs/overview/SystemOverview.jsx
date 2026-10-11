import OverviewActivityChart from './OverviewActivityChart'
import OverviewDataTable from './OverviewDataTable'
import MpSelect from '../../MpSelect'
import { overviewDateKey } from '../../../utils/systemOverview'

const PERIODS = [{ value: 'day', label: 'By day' }, { value: 'week', label: 'By week' },
  { value: 'month', label: 'By month' }, { value: 'year', label: 'By year' }]
const number = (value) => Number(value ?? 0).toLocaleString('en-PH')
const pestLabel = (value) => ({ cecid: 'Fruit-attacking Cecid', fruitfly: 'Oriental Fruit Fly' }[value] || value)
const dateLabel = (value) => new Date(value).toLocaleDateString('en-PH', {
  timeZone: 'Asia/Manila', year: 'numeric', month: 'short', day: 'numeric',
})
const countColumn = (key, label) => ({ key, label, numeric: true, value: (row) => row[key], format: number })
const ORCHARD_COLUMNS = [
  { key: 'name', label: 'Orchard', value: (row) => row.name },
  { ...countColumn('tree_count', 'Trees'), format: (value) => value == null ? '—' : number(value) },
  countColumn('simulations', 'Completed runs'), countColumn('observations', 'Inspections'),
  countColumn('present', 'Present'), countColumn('alerts', 'Alerts raised'), countColumn('active_alerts', 'Active now'),
]
const PEST_COLUMNS = [{ key: 'pest_type', label: 'Pest', value: (row) => pestLabel(row.pest_type) },
  countColumn('simulations', 'Completed runs'), countColumn('observations', 'Inspections'), countColumn('present', 'Present')]
const orchardRowKey = (row) => row.orchard_id ?? 'unassigned'
const pestRowKey = (row) => row.pest_type

function Kpi({ icon, title, value, detail, color = 'text-success' }) {
  return <div className="col-12 col-sm-6 col-xl-4">
    <div className="card monitoring-kpi-card h-100"><div className="card-body p-3 d-flex gap-3">
      <div className="monitoring-kpi-icon"><i className={`bi bi-${icon} ${color} fs-4`} aria-hidden="true" /></div>
      <div><p className="monitoring-kpi-label mb-1">{title}</p>
        <div className="monitoring-kpi-value mb-1">{number(value)}</div>
        <div className="overview-kpi-detail text-muted">{detail}</div></div>
    </div></div>
  </div>
}

export default function SystemOverview({ data, loading, refreshing = false, error, refreshError = '', period, selectedDate, orchardId, directory = [],
  onPeriodChange, onDateChange, onOrchardChange, onRefresh }) {
  const hasActivity = data && (data.simulations.total + data.observations.total + data.alerts.raised > 0)
  const orchardOptions = [{ value: '', label: 'All orchards' },
    ...(orchardId && !directory.some((row) => row.orchard_id === orchardId) ? [{ value: orchardId, label: orchardId }] : []),
    ...directory.map((row) => ({ value: row.orchard_id, label: row.name }))]
  const orchardName = orchardOptions.find((option) => option.value === orchardId)?.label
  const monthly = period === 'month'
  return <section className="system-overview p-3" aria-label="System overview" aria-busy={loading || refreshing}>
    <div className="card monitoring-module-chart-card overview-header-card mb-3">
      <div className="card-header" data-tour="overview-heading">
        <div className="overview-header-row">
          <div className="overview-header-copy">
            <h1 className="overview-panel-title mb-1"><i className="bi bi-grid-1x2 me-2" aria-hidden="true" />System Overview</h1>
            <p className="overview-subtitle mb-0">{orchardName} — saved activity and field inspections</p>
          </div>
          <div className="overview-filters">
            <div className="overview-orchard-filter">
              <MpSelect id="overview-orchard" ariaLabel="Overview orchard" small className="mb-0"
                value={orchardId} options={orchardOptions} onChange={onOrchardChange} />
            </div>
            <div className="history-period-filter overview-period-filter">
              <label className="history-month-picker overview-date-picker active" htmlFor="overview-date">
                <i className="bi bi-calendar3" aria-hidden="true" />
                <span className="visually-hidden">{monthly ? 'Overview month and year' : 'Overview date'}</span>
                <input id="overview-date" type={monthly ? 'month' : 'date'}
                  value={monthly ? selectedDate.slice(0, 7) : selectedDate}
                  max={monthly ? overviewDateKey().slice(0, 7) : overviewDateKey()}
                  aria-label={monthly ? 'Overview month and year' : 'Overview date'} required aria-describedby="overview-date-help"
                  onChange={(event) => { if (event.target.value) onDateChange(monthly ? `${event.target.value}-01` : event.target.value) }} />
              </label>
            </div>
            <div className="overview-period-select">
              <MpSelect id="overview-period" ariaLabel="Overview period" ariaDescribedBy="overview-date-help"
                small className="mb-0" value={period} options={PERIODS} onChange={onPeriodChange} />
            </div>
            <button type="button" className="btn btn-sm btn-outline-secondary" onClick={onRefresh} disabled={loading || refreshing}>
              {loading || refreshing ? <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />
                : <i className="bi bi-arrow-clockwise me-1" aria-hidden="true" />}Refresh
            </button>
          </div>
        </div>
      </div>
      <div className="card-body overview-scope">
        <p id="overview-date-help" className="mb-0">Choose a day, Monday–Sunday week, calendar month or year in Philippine time.</p>
        {data && <span className="overview-range"><i className="bi bi-calendar-range me-1" aria-hidden="true" />{dateLabel(data.start_at)} – {dateLabel(data.end_at)}</span>}
      </div>
    </div>
    {loading && <div className="overview-status" role="status"><span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />Loading saved activity…</div>}
    {refreshing && <p className="small text-muted" role="status"><span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />Updating saved activity…</p>}
    {error && <div className="alert alert-danger" role="alert">{error} Use Refresh to try again.</div>}
    {refreshError && <div className="alert alert-warning" role="alert">{refreshError} Showing the last loaded records. Use Refresh to try again.</div>}
    {!loading && !error && data && <>
      <div className="row g-3 mb-3">
        <Kpi icon="geo-alt" title="Registered orchards" value={data.inventory.orchards}
          detail={`${number(data.inventory.monitored_orchards)} currently monitored · current inventory`} />
        <Kpi icon="tree-fill" title="Registered trees" value={data.inventory.trees} detail="Current orchard inventory" />
        <Kpi icon="cpu" title="Completed simulations" value={data.simulations.completed} color="text-primary"
          detail={`${number(data.simulations.failed)} failed · ${number(data.simulations.other)} other · in this period`} />
        <Kpi icon="clipboard2-check" title="Inspection records" value={data.observations.inspected}
          detail={`${number(data.observations.absent)} absent · ${number(data.observations.not_inspected)} not inspected (excluded) · in this period`} />
        <Kpi icon="bug" title="Present findings" value={data.observations.present} color="text-danger"
          detail="Field records reporting pest presence in this period" />
        <Kpi icon="bell-fill" title="Active alerts now" value={data.alerts.active} color="text-warning"
          detail={`${number(data.alerts.high_critical_active)} high/critical now · ${number(data.alerts.raised)} alerts raised in this period`} />
      </div>
      {!hasActivity && <div className="alert alert-light border" role="status">
        No saved activity in this period. Choose another date, period or orchard to review other records.
      </div>}
      <div className="card monitoring-module-chart-card mb-3">
        <div className="card-header"><h2 className="overview-panel-title mb-0"><i className="bi bi-bar-chart me-2" aria-hidden="true" />Activity over time</h2></div>
        <div className="card-body">
        <OverviewActivityChart timeline={data.timeline} monthly={period === 'year'} />
      </div></div>
      <div className="row g-3 mb-3">
        <div className="col-12 col-xxl-7"><div className="card monitoring-module-chart-card">
          <div className="card-header"><h2 className="overview-panel-title mb-0"><i className="bi bi-tree me-2" aria-hidden="true" />Orchard activity</h2></div>
          <div className="card-body">
          <OverviewDataTable id="overview-orchard-activity" label="Orchard activity" rows={data.orchard_activity}
            columns={ORCHARD_COLUMNS} rowKey={orchardRowKey} emptyMessage="No registered orchards or saved activity."
            caption="Runs, inspections and alerts raised use the selected period. Trees and active alerts are current counts." />
        </div></div></div>
        <div className="col-12 col-xxl-5"><div className="card monitoring-module-chart-card">
          <div className="card-header"><h2 className="overview-panel-title mb-0"><i className="bi bi-bug me-2" aria-hidden="true" />Activity by pest</h2></div>
          <div className="card-body">
          <OverviewDataTable id="overview-pest-activity" label="Activity by pest" rows={data.pests}
            columns={PEST_COLUMNS} rowKey={pestRowKey} />
        </div></div></div>
      </div>
      <div className="overview-notes text-muted">
      <p className="mb-1">Inspections count field records; repeat visits to the same tree are counted separately.
        Present findings are included in inspection records. Simulation counts describe saved scenarios; individual outcomes are available in Results and History.</p>
      <p className="mb-0">This overview includes records saved to the application database.
        Current model: {data.current_model_version}. Updated {new Date(data.computed_at).toLocaleTimeString('en-PH', { timeZone: 'Asia/Manila', hour: '2-digit', minute: '2-digit' })} Philippine time.</p>
      </div>
    </>}
  </section>
}
