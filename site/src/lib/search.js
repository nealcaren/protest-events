import Fuse from 'fuse.js'

let fuseInstance = null

export function buildSearchIndex(events) {
  fuseInstance = new Fuse(events, {
    keys: [
      { name: 'description', weight: 3 },
      { name: 'organizations', weight: 2 },
      { name: 'individuals', weight: 2 },
      { name: 'target', weight: 1 },
    ],
    threshold: 0.3,
    includeScore: true,
  })
  return fuseInstance
}

export function searchEvents(query) {
  if (!fuseInstance || !query.trim()) return null
  return fuseInstance.search(query).map(r => r.item)
}
