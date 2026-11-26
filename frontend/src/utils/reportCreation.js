// All creation entry points honor the writing method selected in the same dialog.
export function createdReportRoute(id, options = {}) {
  const query = options.writingMode === 'ai'
    ? { ai: options.collaboration === 'shared' && !options.assignmentsReady ? 'setup' : '1' }
    : {};
  return { name: 'editor', params: { id }, query };
}
