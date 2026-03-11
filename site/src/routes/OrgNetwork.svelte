<script>
  import { onMount } from 'svelte'
  import { loadOrgNetwork, loadOrgs } from '../lib/api.js'
  import * as d3 from 'd3'
  import { ISSUE_COLORS } from '../lib/utils.js'

  let container
  let tooltip = { show: false, x: 0, y: 0, name: '', count: 0, issue: '' }
  let networkData = null
  let orgIdMap = {}

  onMount(async () => {
    const [network, orgs] = await Promise.all([loadOrgNetwork(), loadOrgs()])
    networkData = network
    orgIdMap = Object.fromEntries(orgs.map(o => [o.id, o]))
    if (network.nodes.length > 0) {
      buildGraph(network)
    }
  })

  function buildGraph(data) {
    const width = container.clientWidth
    const height = Math.max(600, window.innerHeight - 200)

    const svg = d3.select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', [0, 0, width, height])

    // Scale node size by event count
    const maxEvents = d3.max(data.nodes, d => d.event_count) || 1
    const radiusScale = d3.scaleSqrt()
      .domain([1, maxEvents])
      .range([4, 40])

    // Scale edge width by weight
    const maxWeight = d3.max(data.edges, d => d.weight) || 1
    const edgeScale = d3.scaleLinear()
      .domain([1, maxWeight])
      .range([1, 6])

    const simulation = d3.forceSimulation(data.nodes)
      .force('link', d3.forceLink(data.edges).id(d => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => radiusScale(d.event_count) + 4))

    // Edges
    const link = svg.append('g')
      .selectAll('line')
      .data(data.edges)
      .join('line')
      .attr('stroke', '#ccc')
      .attr('stroke-width', d => edgeScale(d.weight))
      .attr('stroke-opacity', 0.6)

    // Nodes
    const node = svg.append('g')
      .selectAll('g')
      .data(data.nodes)
      .join('g')
      .call(d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended))
      .style('cursor', 'pointer')

    node.append('circle')
      .attr('r', d => radiusScale(d.event_count))
      .attr('fill', d => getColor(d.issue_primary))
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5)
      .attr('opacity', 0.85)

    // Labels for larger nodes
    node.filter(d => d.event_count >= 10)
      .append('text')
      .text(d => truncateName(d.name))
      .attr('text-anchor', 'middle')
      .attr('dy', d => radiusScale(d.event_count) + 14)
      .attr('font-size', '11px')
      .attr('font-weight', '600')
      .attr('fill', '#333')
      .attr('pointer-events', 'none')

    // Hover
    node.on('mouseover', (event, d) => {
      tooltip = {
        show: true,
        x: event.pageX,
        y: event.pageY,
        name: d.name,
        count: d.event_count,
        issue: d.issue_primary || ''
      }
    })
    .on('mousemove', (event) => {
      tooltip.x = event.pageX
      tooltip.y = event.pageY
      tooltip = tooltip
    })
    .on('mouseout', () => {
      tooltip = { ...tooltip, show: false }
    })
    .on('click', (event, d) => {
      const org = orgIdMap[d.id]
      if (org) window.location.hash = `/orgs/${org.id}`
    })

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y)
      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })

    function dragstarted(event) {
      if (!event.active) simulation.alphaTarget(0.3).restart()
      event.subject.fx = event.subject.x
      event.subject.fy = event.subject.y
    }
    function dragged(event) {
      event.subject.fx = event.x
      event.subject.fy = event.y
    }
    function dragended(event) {
      if (!event.active) simulation.alphaTarget(0)
      event.subject.fx = null
      event.subject.fy = null
    }
  }

  function getColor(issue) {
    const colors = {
      anti_lynching: '#dc2626',
      segregation_public: '#ea580c',
      voting_rights: '#2563eb',
      civil_rights_organizing: '#7c3aed',
      labor: '#0891b2',
      education: '#059669',
      military: '#4b5563',
      government_discrimination: '#b91c1c',
      criminal_justice: '#92400e',
      pan_african: '#15803d',
      cultural_media: '#9333ea',
      housing: '#c2410c',
      healthcare: '#0d9488',
      womens_organizing: '#be185d',
      migration: '#6366f1',
    }
    return colors[issue] || '#6b7280'
  }

  function truncateName(name) {
    return name.length > 25 ? name.slice(0, 23) + '...' : name
  }
</script>

<div class="network-page">
  <div class="page-header">
    <a href="#/orgs" class="back-link">&larr; Organizations</a>
    <h1>Organization Network</h1>
    <p class="subtitle">Organizations connected by co-occurrence in protest events. Node size = event count. Click a node to view details.</p>
  </div>

  <div class="graph-container" bind:this={container}></div>

  {#if tooltip.show}
    <div class="tooltip" style="left: {tooltip.x + 12}px; top: {tooltip.y - 8}px;">
      <strong>{tooltip.name}</strong>
      <div>{tooltip.count} events</div>
      {#if tooltip.issue}<div class="tt-issue">{tooltip.issue.replace(/_/g, ' ')}</div>{/if}
    </div>
  {/if}

  <div class="legend">
    <h3>Issues</h3>
    <div class="legend-items">
      {#each Object.entries({
        anti_lynching: 'Anti-Lynching',
        voting_rights: 'Voting Rights',
        civil_rights_organizing: 'Civil Rights',
        labor: 'Labor',
        education: 'Education',
        pan_african: 'Pan-African',
        military: 'Military',
        segregation_public: 'Segregation',
      }) as [key, label]}
        <div class="legend-item">
          <span class="legend-dot" style="background: {getColor(key)}"></span>
          {label}
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .network-page { padding-top: 24px; }
  .page-header { margin-bottom: 16px; }
  .back-link {
    font-size: 0.85rem; color: #888; text-decoration: none;
  }
  .back-link:hover { color: #1a1a1a; }
  h1 { font-size: 1.8rem; font-weight: 800; margin: 8px 0 4px; }
  .subtitle { color: #888; font-size: 0.9rem; }
  .graph-container {
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    overflow: hidden;
    margin-top: 16px;
  }
  .tooltip {
    position: fixed;
    background: #1a1a1a;
    color: white;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.8rem;
    pointer-events: none;
    z-index: 1000;
    max-width: 250px;
  }
  .tooltip strong { display: block; margin-bottom: 2px; }
  .tt-issue { color: #aaa; font-size: 0.75rem; text-transform: capitalize; }
  .legend {
    margin-top: 16px;
    padding: 12px 16px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  .legend h3 {
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em;
    color: #888; margin-bottom: 8px;
  }
  .legend-items {
    display: flex; flex-wrap: wrap; gap: 12px;
  }
  .legend-item {
    display: flex; align-items: center; gap: 6px;
    font-size: 0.8rem;
  }
  .legend-dot {
    width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
  }
</style>
