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
SIMILARITY_THRESHOLD = 0.50
MAX_CANDIDATES_PER_QUERY = 200

# Seed queries — derived from actual newspaper language via sample coding
SEED_QUERIES = [
    # Collective action and mobilization
    "colored citizens up in arms and threaten to make trouble against discriminatory practices",
    "appeal to colored people to come together and march forward for justice",
    "active and organized protests of colored women backed by numerous organizations",
    "mass meeting held to discuss school conditions and organize for educational equality",
    # Anti-lynching
    "national association made public telegrams sent to governors with reference to lynchings",
    "effort will be made to severely punish those responsible for mob violence",
    "first national conference on lynching examining causes and demanding federal action",
    "speakers denounced the lynching and called for federal legislation to stop mob rule",
    # Delegations and petitions
    "protest to the president against riots and lynchings seeking public word of hope",
    "committee of graduates written condemning jim crow policy and demanding segregation be discontinued",
    "colored men representing political league called upon presidential candidate for interview",
    "a committee of prominent colored citizens called upon the governor to present a petition",
    # NAACP and organizational
    "delegates to annual conference demands equal rights and attacks lynching",
    "national association made address to american people at annual conference",
    "investigation made by the national association regarding disregard for constitutional rights",
    "federal council of churches takes emphatic stand for enforcement of constitutional amendments",
    # Labor and economic
    "strike by workers against company discrimination in employment practices",
    "colored workers refused to return to work until the Jim Crow conditions were removed",
    "a boycott was declared against the stores that refused to serve Negro customers",
    # Legislative and political protest
    "opposing confirmation of colored nominee through concerted action by senators",
    "questionnaires sent to presidential aspirants regarding their stance on racial equality",
    "colored citizens object to history textbooks and railroad discrimination",
    # Marches and parades
    "a large procession of Negro men and women marched through the streets bearing signs",
    "thousands of colored citizens marched silently down the avenue in protest",
    # Race riots and defense
    "rioting broke out when a mob attacked the colored section of the city",
]

# Classification
HAIKU_MODEL = "claude-haiku-4-5-20251001"

SITE_BASE_URL = "https://dangerouspress.org"
