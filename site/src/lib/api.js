let eventsCache = null
let campaignsCache = null
let metaCache = null
let orgsCache = null
let orgNetworkCache = null

export async function loadEvents() {
  if (!eventsCache) {
    const res = await fetch('./data/events.json')
    eventsCache = await res.json()
  }
  return eventsCache
}

export async function loadEvent(id) {
  const events = await loadEvents()
  return events.find(e => e.id === Number(id)) || null
}

export async function loadCampaigns() {
  if (!campaignsCache) {
    const res = await fetch('./data/campaigns.json')
    campaignsCache = await res.json()
  }
  return campaignsCache
}

export async function loadCampaign(id) {
  const campaigns = await loadCampaigns()
  return campaigns.find(c => c.id === Number(id)) || null
}

export async function loadMeta() {
  if (!metaCache) {
    const res = await fetch('./data/meta.json')
    metaCache = await res.json()
  }
  return metaCache
}

export async function loadOrgs() {
  if (!orgsCache) {
    const res = await fetch('./data/organizations.json')
    orgsCache = await res.json()
  }
  return orgsCache
}

export async function loadOrg(id) {
  const orgs = await loadOrgs()
  return orgs.find(o => o.id === Number(id)) || null
}

export async function loadOrgNetwork() {
  if (!orgNetworkCache) {
    const res = await fetch('./data/org_network.json')
    orgNetworkCache = await res.json()
  }
  return orgNetworkCache
}
