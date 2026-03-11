"""Configuration for the protest event pipeline."""

from pathlib import Path

# Paths
OCR_DIR = Path(__file__).parent / "ocr-results"
DATA_DIR = Path(__file__).parent / "data"

EMBEDDINGS_FILE = DATA_DIR / "embeddings.npy"
DB_FILE = DATA_DIR / "protest_events.db"
REPORT_FILE = DATA_DIR / "events.html"

# Embedding model (local, via sentence-transformers)
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1.5"

# Search config
SIMILARITY_THRESHOLD = 0.70
MAX_CANDIDATES_PER_QUERY = 200

# Seed queries — organized by event type, using period-authentic newspaper language.
# Each group targets a specific form of collective political action.
SEED_QUERIES = [
    # --- Anti-lynching campaigns ---
    "effort will be made to severely punish those responsible for mob violence",
    "speakers denounced the lynching and called for federal legislation to stop mob rule",
    "first national conference on lynching examining causes and demanding federal action",
    "national association made public telegrams sent to governors with reference to lynchings",
    "ringing declarations against mob violence signed by governors judges and club women",
    "Anti-Lynching Crusaders launched campaign to unite million women against mob murder",
    # --- Marches, parades, and demonstrations ---
    "a large procession of Negro men and women marched through the streets bearing signs",
    "thousands of colored citizens marched silently down the avenue in protest",
    "colored citizens up in arms and threaten to make trouble against discriminatory practices",
    "silent parade of thousands marched down Fifth Avenue to protest the East St Louis massacre",
    "citizens organized protest demonstration against showing of The Birth of a Nation picture",
    # --- Mass meetings and rallies ---
    "mass meeting held to discuss school conditions and organize for educational equality",
    "magnificent audience gathered at the academy to protest against mob murder and call upon Congress",
    "indignation meeting called by colored citizens to take action against the outrage",
    "church congregation adopted resolutions condemning racial injustice and pledging united action",
    "ministers meeting at Baptist convention passed resolutions demanding equal treatment",
    # --- Delegations and petitions ---
    "a committee of prominent colored citizens called upon the governor to present a petition",
    "protest to the president against riots and lynchings seeking public word of hope",
    "colored men representing political league called upon presidential candidate for interview",
    "colored citizens sent numerous requests to the court demanding that one of their own be appointed",
    # --- NAACP and civil rights organizations ---
    "delegates to annual conference demands equal rights and attacks lynching",
    "national association made address to american people at annual conference",
    "newly organized association of colored citizens aims to fight discrimination in the courts",
    "resolutions were adopted urging Congress to pass the Dyer Anti-Lynching bill",
    # --- Niagara Movement and early civil rights organizations ---
    "members of the Niagara Movement met to demand full civil rights and an end to discrimination",
    "National Equal Rights League organized to secure by appeals to courts full citizenship rights",
    "delegates of the Afro-American Council assembled to consider the condition of the race",
    # --- Urban League and social welfare organizing ---
    "National Urban League conducted investigation of conditions among Negro migrants in the city",
    "Urban League organized campaign to secure employment opportunities for colored workers",
    # --- Pan-African and international solidarity ---
    "delegates from colored nations assembled at the Pan-African Congress to consider world problems",
    "African Blood Brotherhood organized for liberation and self-defense of the Negro race",
    # --- Boycotts and economic protest ---
    "a boycott was declared against the stores that refused to serve Negro customers",
    "inaugurate a crusade to put him out of business by withdrawing colored patronage",
    "colored taxpayers protest their exclusion from public facilities for which they are compelled to pay",
    "colored passengers refused to ride the streetcars until jim crow regulations were abolished",
    "tenants organized rent strike against landlords who charge exorbitant rents for colored housing",
    # --- Labor and strikes ---
    "colored workers refused to return to work until the Jim Crow conditions were removed",
    "strike by workers against company discrimination in employment practices",
    "member of the Brotherhood of Sleeping Car Porters persecuted by the railroad for his union activities",
    "colored washerwomen organized and declared they would not work for less than a living wage",
    # --- Peonage and convict lease resistance ---
    "investigation revealed conditions of peonage and forced labor in the southern labor camps",
    "efforts made to secure release of colored men held in virtual slavery under the convict lease system",
    # --- Voter mobilization and electoral organizing ---
    "colored voters are urged to register and go to the polls in full force for the coming election",
    "effort is being made to line up the colored voters of the city and carry their fight to all sections",
    "colored Republicans making concerted effort to resist the lily-white movement in the southern states",
    "Alpha Suffrage Club organized colored women to register and exercise the right of franchise",
    # --- Legislative action ---
    "colored assemblyman introduced measures in the legislature to protect the rights of his race",
    "committee of graduates written condemning jim crow policy and demanding segregation be discontinued",
    "questionnaires sent to presidential aspirants regarding their stance on racial equality",
    # --- Armed self-defense and race riots ---
    "rioting broke out when a mob attacked the colored section of the city",
    "armed colored men defended themselves when the mob advanced upon the Negro district",
    "colored residents organized to protect their homes and families against the rioters",
    # --- Anti-KKK organizing ---
    "citizens organized to oppose the Ku Klux Klan and demanded officials take action against night riders",
    "mass meeting called to protest the outrages committed by the hooded order in the community",
    # --- Legal campaigns and test cases ---
    "race attorneys filed suit demanding that the court compel compliance with constitutional rights",
    "investigation made by the national association regarding disregard for constitutional rights",
    "suit brought to compel the company to render a full accounting and restore the rights of the race",
    "case brought to test the constitutionality of the residential segregation ordinance",
    "suit filed challenging the white primary law that bars colored citizens from voting",
    "property owners organized to fight restrictive covenants barring colored families from the neighborhood",
    # --- School and education equity ---
    "colored citizens appeared before the school board to demand equal school facilities for their children",
    "asked that the Board open a Junior High School for colored pupils to relieve overcrowded conditions",
    "students walked out of school to protest the appointment of a white principal over colored teachers",
    # --- Great Migration as collective action ---
    "thousands of colored families leaving the South in protest against conditions of oppression",
    "labor agents and ministers organized the exodus of colored workers from southern plantations",
    # --- UNIA and Garveyism ---
    "Universal Negro Improvement Association held mass meeting at Liberty Hall with thousands in attendance",
    "delegates assembled at the annual convention of the UNIA to consider the welfare of the Negro peoples",
    # --- Fraternal orders and mutual aid activism ---
    "lodge members of the Odd Fellows assembled in convention to adopt resolutions on behalf of the race",
    "Knights of Pythias organized relief fund and protest committee in response to the crisis",
    # --- Women's club activism ---
    "National Association of Colored Women gathered in convention to adopt resolutions on the race question",
    "active and organized protests of colored women backed by numerous organizations",
    "colored women organized campaign for mothers pensions and protection of working girls",
    # --- Military inclusion ---
    "colored citizens have for months been advocating the addition of a colored regiment to the national guard",
    "petition sent to the war department urging the appointment of colored officers for colored troops",
    "colored soldiers protested the indignities heaped upon them while in uniform serving their country",
    # --- Anti-police brutality ---
    "colored citizens directed to take the number of every police officer who commits an outrage",
    "affidavits are being gathered from colored men and women taken to jail without cause",
    # --- Clemency and prisoner advocacy ---
    "friends of the colored man are making every effort to secure his pardon from the governor",
    "a movement is on foot among citizens to lay before the governor the facts and secure his release",
]

# Classification (via OpenRouter)
CLASSIFIER_MODEL = "qwen/qwen3-235b-a22b-2507"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SITE_BASE_URL = "https://dangerouspress.org"

# Newspaper publication locations
PAPER_LOCATIONS = {
    "amsterdam-news": "New York, NY",
    "athens-republique": "Athens, GA",
    "baltimore-afro-american": "Baltimore, MD",
    "broad-ax": "Chicago, IL",
    "chicago-defender": "Chicago, IL",
    "chicago-whip": "Chicago, IL",
    "cleveland-gazette": "Cleveland, OH",
    "colorado-statesman": "Denver, CO",
    "dallas-express": "Dallas, TX",
    "denver-star": "Denver, CO",
    "houston-informer": "Houston, TX",
    "indianapolis-freeman": "Indianapolis, IN",
    "iowa-bystander": "Des Moines, IA",
    "kansas-city-advocate": "Kansas City, MO",
    "kansas-city-sun": "Kansas City, MO",
    "metropolis-weekly-gazette": "Metropolis, IL",
    "montana-plaindealer": "Helena, MT",
    "muskogee-cimeter": "Muskogee, OK",
    "nashville-globe": "Nashville, TN",
    "negro-world": "New York, NY",
    "new-york-age": "New York, NY",
    "omaha-monitor": "Omaha, NE",
    "phoenix-tribune": "Phoenix, AZ",
    "pittsburgh-courier": "Pittsburgh, PA",
    "portland-new-age": "Portland, OR",
    "raleigh-independent": "Raleigh, NC",
    "richmond-planet": "Richmond, VA",
    "springfield-forum": "Springfield, IL",
    "st-louis-argus": "St. Louis, MO",
    "st-paul-appeal": "St. Paul, MN",
    "tulsa-star": "Tulsa, OK",
    "twin-city-star": "Minneapolis, MN",
    "washington-bee": "Washington, DC",
    "washington-tribune": "Washington, DC",
    "western-outlook": "Oakland, CA",
    "wichita-searchlight": "Wichita, KS",
    "wisconsin-weekly-blade": "Milwaukee, WI",
}

ISSUE_CATEGORIES = [
    "anti_lynching",
    "segregation_public",
    "education",
    "voting_rights",
    "labor",
    "criminal_justice",
    "military",
    "government_discrimination",
    "housing",
    "healthcare",
    "cultural_media",
    "civil_rights_organizing",
    "pan_african",
    "womens_organizing",
    "migration",
]
