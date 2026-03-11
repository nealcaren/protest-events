<script>
  export let currentPage = 1
  export let totalPages = 1
  import { createEventDispatcher } from 'svelte'

  const dispatch = createEventDispatcher()

  function goTo(page) {
    if (page >= 1 && page <= totalPages) {
      dispatch('page', page)
    }
  }

  $: pages = Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
    if (totalPages <= 7) return i + 1
    if (currentPage <= 4) return i + 1
    if (currentPage >= totalPages - 3) return totalPages - 6 + i
    return currentPage - 3 + i
  })
</script>

{#if totalPages > 1}
  <nav class="pagination">
    <button on:click={() => goTo(currentPage - 1)} disabled={currentPage === 1}>
      Prev
    </button>
    {#each pages as p}
      <button class:active={p === currentPage} on:click={() => goTo(p)}>
        {p}
      </button>
    {/each}
    <button on:click={() => goTo(currentPage + 1)} disabled={currentPage === totalPages}>
      Next
    </button>
  </nav>
{/if}

<style>
  .pagination {
    display: flex;
    gap: 4px;
    justify-content: center;
    margin: 32px 0;
  }
  button {
    padding: 8px 14px;
    border: 1px solid #ddd;
    background: white;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85rem;
  }
  button:hover:not(:disabled) {
    background: #f5f5f5;
  }
  button:disabled {
    opacity: 0.4;
    cursor: default;
  }
  button.active {
    background: #1a1a1a;
    color: white;
    border-color: #1a1a1a;
  }
</style>
