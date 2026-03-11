const SITE_BASE_URL = 'https://dangerouspress.org'

export const ISSUE_LABELS = {
  anti_lynching: 'Anti-Lynching',
  segregation_public: 'Segregation',
  education: 'Education',
  voting_rights: 'Voting Rights',
  labor: 'Labor',
  criminal_justice: 'Criminal Justice',
  military: 'Military',
  government_discrimination: "Gov't Discrimination",
  housing: 'Housing',
  healthcare: 'Healthcare',
  cultural_media: 'Cultural/Media',
  civil_rights_organizing: 'Civil Rights Org.',
  pan_african: 'Pan-African',
  womens_organizing: "Women's Organizing",
  migration: 'Migration',
}

export const ISSUE_COLORS = {
  anti_lynching: '#c0392b',
  segregation_public: '#2980b9',
  education: '#27ae60',
  voting_rights: '#8e44ad',
  labor: '#d35400',
  criminal_justice: '#2c3e50',
  military: '#16a085',
  government_discrimination: '#7f8c8d',
  housing: '#f39c12',
  healthcare: '#1abc9c',
  cultural_media: '#e74c3c',
  civil_rights_organizing: '#3498db',
  pan_african: '#9b59b6',
  womens_organizing: '#e67e22',
  migration: '#95a5a6',
}

export function makeViewerUrl(paper, date, page, chunkIdx) {
  let url = `${SITE_BASE_URL}/?paper=${paper}&date=${date}&page=${page}`
  if (chunkIdx != null) {
    url += `#chunk-${chunkIdx}`
  }
  return url
}

export function formatPaperName(slug) {
  return slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export function formatLocation(city, state) {
  if (city && state) return `${city}, ${state}`
  if (state) return state
  if (city) return city
  return null
}
