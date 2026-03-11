import { writable } from 'svelte/store'

export const currentPath = writable(window.location.hash.slice(1) || '/')
export const currentParams = writable({})

window.addEventListener('hashchange', () => {
  currentPath.set(window.location.hash.slice(1) || '/')
})

export function navigate(path) {
  window.location.hash = path
}

export function matchRoute(path, pattern) {
  // pattern like "/events/:id" matches "/events/123"
  const patternParts = pattern.split('/')
  const pathParts = path.split('/')

  if (patternParts.length !== pathParts.length) return null

  const params = {}
  for (let i = 0; i < patternParts.length; i++) {
    if (patternParts[i].startsWith(':')) {
      params[patternParts[i].slice(1)] = pathParts[i]
    } else if (patternParts[i] !== pathParts[i]) {
      return null
    }
  }
  return params
}
