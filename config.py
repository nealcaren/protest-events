"""Configuration for the protest event pipeline."""

from pathlib import Path

# Paths
OCR_DIR = Path("/tmp/longleaf-ocr-results/ocr-results")
DATA_DIR = Path(__file__).parent / "data"

EMBEDDINGS_FILE = DATA_DIR / "embeddings.npz"
METADATA_FILE = DATA_DIR / "metadata.csv"
CANDIDATES_FILE = DATA_DIR / "candidates.csv"
EVENTS_FILE = DATA_DIR / "events.csv"
REPORT_FILE = DATA_DIR / "events.html"

# Embedding model (OpenAI API)
EMBEDDING_MODEL = "text-embedding-3-small"

# Search config
SIMILARITY_THRESHOLD = 0.70
MAX_CANDIDATES_PER_QUERY = 200

# Seed queries — refined after exploring 1K sample results
SEED_QUERIES = [
    # Direct action
    "protest march through the streets",
    "demonstration against discrimination",
    "mass meeting held to protest",
    "silent protest parade",
    "parade through the city",
    # Petitions and delegations
    "petition signed by citizens",
    "delegation presented demands",
    "citizens assembled to protest",
    "committee waited upon the governor",
    # Anti-lynching movement
    "mass protest against lynching",
    "anti-lynching crusade",
    "NAACP protests against lynching",
    # Racial violence and resistance
    "race riot",
    "mob violence against Negroes",
    "colored citizens organize for defense",
    # Labor and economic
    "workers went on strike",
    "boycott of stores",
    "laborers on strike",
    # Civil rights actions
    "protest against Jim Crow",
    "fight against segregation",
    "demand equal rights for Negroes",
    "revolt against discrimination",
]

# Classification
HAIKU_MODEL = "claude-haiku-4-5-20251001"

SITE_BASE_URL = "https://dangerouspress.org"
