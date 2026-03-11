<script>
  import { ISSUE_LABELS, ISSUE_COLORS } from '../lib/utils.js'

  export let type = 'issue'
  export let value = ''

  $: label = type === 'issue' ? (ISSUE_LABELS[value] || value) : value
  $: color = type === 'issue' ? (ISSUE_COLORS[value] || '#666') : null
</script>

{#if value}
  <span
    class="badge badge-{type}"
    style={color ? `--badge-color: ${color}` : ''}
  >
    {label}
  </span>
{/if}

<style>
  .badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    white-space: nowrap;
  }
  .badge-issue {
    background: color-mix(in srgb, var(--badge-color) 15%, white);
    color: var(--badge-color);
  }
  .badge-event_type {
    background: #f0f0f0;
    color: #444;
  }
  .badge-campaign {
    background: #eee8f5;
    color: #5a3d8a;
  }
  .badge-tactic {
    background: #e8f4e8;
    color: #2d6a2d;
  }
</style>
