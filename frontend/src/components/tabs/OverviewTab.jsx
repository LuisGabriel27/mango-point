import { useEffect, useState } from 'react'
import api, { apiErrorMessage } from '../../api'
import { failOverviewLoad, overviewDateKey, requestSystemOverview, startOverviewLoad } from '../../utils/systemOverview'
import SystemOverview from './overview/SystemOverview'

export default function OverviewTab({ active = true, refreshKey = 0 }) {
  const [period, setPeriod] = useState('month')
  const [selectedDate, setSelectedDate] = useState(() => overviewDateKey())
  const [orchardId, setOrchardId] = useState('')
  const [reload, setReload] = useState(0)
  const [directory, setDirectory] = useState([])
  const [state, setState] = useState({ loading: true, data: null, error: '' })
  const requestKey = `${period}:${orchardId}:${selectedDate}`

  useEffect(() => {
    if (!active) return undefined
    setState((previous) => startOverviewLoad(previous, requestKey))
    return requestSystemOverview(api.getSystemOverview,
      { period, date: selectedDate, ...(orchardId ? { orchard_id: orchardId } : {}) },
      (data) => {
        setDirectory(data.orchards)
        setState({ key: requestKey, loading: false, refreshing: false, data, error: '', refreshError: '' })
      },
      (error) => setState((previous) => failOverviewLoad(previous, requestKey,
        apiErrorMessage(error, 'Unable to load the overview.'))),
    )
  }, [active, period, orchardId, selectedDate, requestKey, refreshKey, reload])

  useEffect(() => {
    if (!active) return undefined
    const interval = window.setInterval(() => setReload((value) => value + 1), 60_000)
    return () => window.clearInterval(interval)
  }, [active])

  if (!active) return null
  const visibleState = state.key === requestKey ? state : { loading: true, data: null, error: '' }
  return <SystemOverview {...visibleState} period={period} selectedDate={selectedDate} orchardId={orchardId} directory={directory}
    onPeriodChange={setPeriod} onDateChange={(value) => { if (value) setSelectedDate(value) }}
    onOrchardChange={setOrchardId} onRefresh={() => setReload((value) => value + 1)} />
}
