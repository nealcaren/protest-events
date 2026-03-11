import { writable } from 'svelte/store'

export const filters = writable({
  issues: [],
  papers: [],
  dateRange: [1905, 1929],
  tactics: [],
  actorType: '',
  searchText: '',
})

export function resetFilters() {
  filters.set({
    issues: [],
    papers: [],
    dateRange: [1905, 1929],
    tactics: [],
    actorType: '',
    searchText: '',
  })
}
