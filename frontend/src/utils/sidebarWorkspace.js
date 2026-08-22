export const SIDEBAR_WORKFLOWS = [
  { id: 'setup', label: 'Setup', icon: 'sliders' },
  { id: 'simulate', label: 'Simulate', icon: 'play-circle' },
  { id: 'results', label: 'Results', icon: 'graph-up-arrow' },
]

export const DEFAULT_SIDEBAR_WORKFLOW = 'simulate'

export function nextSidebarWorkflowId(activeWorkflow, key) {
  const currentIndex = Math.max(0, SIDEBAR_WORKFLOWS.findIndex(({ id }) => id === activeWorkflow))
  let nextIndex = currentIndex
  if (key === 'ArrowRight') nextIndex = (currentIndex + 1) % SIDEBAR_WORKFLOWS.length
  else if (key === 'ArrowLeft') nextIndex = (currentIndex - 1 + SIDEBAR_WORKFLOWS.length) % SIDEBAR_WORKFLOWS.length
  else if (key === 'Home') nextIndex = 0
  else if (key === 'End') nextIndex = SIDEBAR_WORKFLOWS.length - 1
  return SIDEBAR_WORKFLOWS[nextIndex].id
}

export function sidebarWorkflowForEvent(event, currentWorkflow = DEFAULT_SIDEBAR_WORKFLOW) {
  if (event === 'simulation-success' || event === 'historical-result') return 'results'
  if (event === 'alert-prefill' || event === 'historical-template') return 'simulate'
  return currentWorkflow
}

export function parseStoredSidebarCollapsed(value) {
  return value === 'true'
}
