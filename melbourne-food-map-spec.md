# Melbourne Indian Food Intelligence Map — Technical Specification

## Overview

An interactive, visually stunning geospatial intelligence dashboard that maps Indian cuisine supply, demographic demand, and market opportunity across Melbourne's suburbs. The output is a single-page web application with a full-screen map and a collapsible side panel. The aesthetic target is dark, modern, data-art quality — think Uber's Kepler.gl meets a Bloomberg terminal, but more beautiful.

---

## Tech Stack

| Concern | Library / Tool | Rationale |
|---|---|---|
| Map engine | **Deck.gl** (via `@deck.gl/react`) | GPU-accelerated, handles millions of points, cinematic visual quality |
| Base map tiles | **Mapbox GL JS** | Dark mode tiles, smooth 3D transitions, best-in-class aesthetics |
| Charting (side panel) | **Recharts** | Composable React charts, clean SVG output |
| UI framework | **React + Tailwind CSS** | Component-based, utility styling |
| Data fetching | **TanStack Query (React Query)** | Async data loading with loading states |
| Colour scales | **d3-scale-chromatic** | Research-grade perceptual colour maps |
| Tooltip rendering | **Floating UI** | Pixel-perfect, accessible tooltips |
| Icons | **Lucide React** | Consistent, minimal icon set |
| Animation | **Framer Motion** | Panel transitions and layer fade-ins |

No backend required. All data is loaded as static GeoJSON/CSV files or fetched from public APIs at runtime.

---

## Data Sources & Attributes

### Dataset 1 — Indian Restaurant Supply (Foursquare Open Source Places)
**Source:** `https://huggingface.co/datasets/foursquare/fsq-os-places` (Parquet, filtered for Melbourne + Indian cuisine categories)

Fields to extract and use:

| Attribute | Field Name | Type | Usage |
|---|---|---|---|
| Restaurant name | `name` | string | Tooltip, sidebar |
| Cuisine category | `fsq_category_label` | string | Filter, dot colour |
| Sub-cuisine | `fsq_category_ids` | string[] | Sub-filter (e.g. South Indian vs North Indian vs Sri Lankan) |
| Latitude | `latitude` | float | Map position |
| Longitude | `longitude` | float | Map position |
| Suburb | `locality` | string | Grouping, sidebar table |
| Postcode | `postcode` | string | Join key to ABS data |
| Address | `address` | string | Tooltip |
| Chain vs independent | `chains` (empty = independent) | bool | Filter toggle |

**Cuisine categories to include:**
- Indian Restaurant
- South Indian Restaurant
- North Indian Restaurant
- Sri Lankan Restaurant
- Bangladeshi Restaurant
- Pakistani Restaurant
- Nepalese Restaurant
- Kerala / Malayali (tag manually if present)

---

### Dataset 2 — Indian-Born Population Density (ABS Census 2021)
**Source:** ABS Census TableBuilder or Data by Region API (`https://dbr.abs.gov.au`)
Filter: Country of Birth = India, Geography = SA2 (Statistical Area Level 2)

Fields to extract:

| Attribute | Field Name | Type | Usage |
|---|---|---|---|
| SA2 region name | `sa2_name` | string | Label on map |
| SA2 code | `sa2_code` | string | Join key |
| Indian-born population count | `india_born_count` | int | Choropleth intensity |
| Total population | `total_pop` | int | Compute density % |
| Indian population % | `india_pct` (derived) | float | Choropleth colour scale |
| Median household income | `median_hh_income` | int | Opportunity score layer |
| SA2 GeoJSON boundary | (from ABS ASGS GeoJSON) | Polygon | Choropleth rendering |

**Derived field:**
```
india_pct = india_born_count / total_pop * 100
```

---

### Dataset 3 — Demand Proxy (Google Places API)
**Source:** Google Places API (Text Search: "Indian restaurant" per suburb)

Fields to extract:

| Attribute | Field Name | Type | Usage |
|---|---|---|---|
| Place ID | `place_id` | string | Dedup key |
| Name | `name` | string | Tooltip |
| Rating | `rating` | float | Dot size |
| Review count | `user_ratings_total` | int | Demand signal (primary) |
| Price level | `price_level` | int (0–4) | Filter |
| Lat/lon | `geometry.location` | float pair | Map position |
| Open now | `opening_hours.open_now` | bool | Filter toggle |

**Key derived metric:**
```
demand_score = rating × log10(user_ratings_total + 1)
```
This normalises for both rating quality and volume.

---

### Dataset 4 — City of Melbourne CLUE (Official Open Data)
**Source:** `https://data.melbourne.vic.gov.au` — Café, Restaurant, Bistro Seats dataset (2002–2023)

Fields to use:

| Attribute | Field Name | Type | Usage |
|---|---|---|---|
| Trading name | `trading_name` | string | Label |
| Industry classification | `anzsic4_description` | string | Filter |
| Street address | `street_address` | string | Tooltip |
| Latitude | `latitude` | float | Map position |
| Longitude | `longitude` | float | Map position |
| Indoor seats | `seating_type_indoor` | int | Scale indicator |
| Year | `census_year` | int | Time slider |
| Small area | `clue_small_area` | string | Sub-suburb grouping |

Note: CLUE covers only the City of Melbourne LGA (CBD + inner suburbs). Use alongside Foursquare for completeness.

---

## Visual Design System

### Colour Palette

```
Background:       #0A0E1A   (near-black navy)
Panel background: #111827   (dark slate)
Panel border:     #1F2937   (subtle border)
Text primary:     #F9FAFB   (off-white)
Text secondary:   #9CA3AF   (muted grey)
Accent:           #F59E0B   (amber — Indian spice palette reference)
Accent 2:         #EF4444   (red — high-density signal)
Accent 3:         #10B981   (emerald — opportunity/gap signal)
```

### Map Style
- **Mapbox style:** `mapbox://styles/mapbox/dark-v11` (or custom dark style)
- Initial view: Melbourne CBD, zoom level 10
- Pitch: 20–30 degrees (slight 3D tilt for visual depth)
- Bearing: 0 (north-up)
- Smooth fly-to animation on suburb selection

---

## Map Layers (Deck.gl)

### Layer 1 — SA2 Choropleth (ABS Population Density)
**Deck.gl layer type:** `GeoJsonLayer`

| Property | Value |
|---|---|
| Data | ABS SA2 GeoJSON polygons |
| Fill colour | Continuous scale: `d3.interpolateYlOrRd` mapped to `india_pct` |
| Fill opacity | 0.55 |
| Stroke colour | `#374151` (subtle grey border) |
| Stroke width | 0.5px |
| Pickable | true (hover to show suburb stats) |
| Transition | `{duration: 600}` on colour change |

Colour scale: `0%` → pale yellow → `15%+` → deep red-orange

---

### Layer 2 — Indian Restaurant Points (Foursquare)
**Deck.gl layer type:** `ScatterplotLayer`

| Property | Value |
|---|---|
| Data | Filtered Foursquare places |
| Position | `[longitude, latitude]` |
| Radius | Fixed: 120 metres |
| Fill colour | By sub-cuisine: South Indian = `#F59E0B`, North Indian = `#60A5FA`, Sri Lankan = `#A78BFA`, Other = `#D1D5DB` |
| Stroke colour | `#FFFFFF` at 60% opacity |
| Stroke width | 1.5px |
| Opacity | 0.9 |
| Pickable | true |
| On hover | Tooltip with name, cuisine type, address |

---

### Layer 3 — Demand Heatmap (Google Places review density)
**Deck.gl layer type:** `HeatmapLayer`

| Property | Value |
|---|---|
| Data | Google Places results |
| Weight | `demand_score` (rating × log reviews) |
| Radius pixels | 60 |
| Colour range | `[[0,0,128,0], [0,128,255,100], [255,200,0,200], [255,50,0,255]]` (transparent blue → bright amber → red) |
| Intensity | 1.5 |
| Threshold | 0.05 |
| Visible | Off by default, toggle via layer panel |

---

### Layer 4 — Opportunity Gap Hexbins
**Deck.gl layer type:** `H3HexagonLayer`

This is the most analytically powerful layer — a derived layer computed client-side.

**Computation:**
```
gap_score = india_pct_normalised - supply_density_normalised
```
Where `supply_density_normalised` = number of Indian restaurants per 10,000 Indian-born residents in that SA2.

A high positive `gap_score` = high Indian population, low restaurant supply = **opportunity**.

| Property | Value |
|---|---|
| Resolution | H3 resolution 8 (~460m hexagons) |
| Elevation | `gap_score × 500` metres (high opportunity = tall hex) |
| Fill colour | `d3.interpolateRdYlGn` reversed: red = gap, green = well-served |
| Opacity | 0.75 |
| Material | `{ambient: 0.35, diffuse: 0.8, specular: 0.3}` (3D lighting) |
| Extruded | true |
| Wireframe | false |
| Pickable | true |

This layer gives the map a stunning 3D city-skyline appearance where tall red hexagons literally point to underserved opportunity zones.

---

### Layer 5 — CLUE Historical Points (CBD only)
**Deck.gl layer type:** `ScatterplotLayer` with time filter

| Property | Value |
|---|---|
| Data | Filtered CLUE (Indian restaurant names only, manually tagged) |
| Colour | `#818CF8` (indigo — distinct from Foursquare layer) |
| Radius | 80 metres |
| Visible | Optional, toggle |

---

## UI Components

### App Shell
- Full-screen map (`100vw × 100vh`)
- No scrolling — everything lives within the viewport
- All UI is overlaid on top of the map using absolute positioning

---

### Top Navigation Bar
- Position: top, full width, `backdrop-blur-md` + semi-transparent dark background
- Left: App title — **"Melbourne Indian Food Intelligence"** in white, weight 600, with a small 🍛 or spice motif icon
- Centre: Layer toggle buttons (pill-style, amber highlight when active):
  - `Population Density` | `Restaurants` | `Demand Heat` | `Opportunity Gaps` | `CLUE History`
- Right: Time period selector (slider or dropdown) for CLUE year filter

---

### Left Side Panel
- Position: Left edge, `380px` wide, `calc(100vh - 60px)` tall
- Background: `#111827` with `backdrop-blur`
- Collapsed by default on mobile, open on desktop
- Toggle: Chevron button on panel edge, animated with Framer Motion

**Panel sections (accordion-style, each expandable):**

#### Section 1 — Suburb Summary
Shown when a suburb polygon is hovered/clicked.
- Suburb name (large, white)
- Indian-born population: count + % of suburb
- Median household income
- Number of Indian restaurants (Foursquare count)
- Demand score (Google Places aggregate)
- Gap score with colour-coded badge: 🔴 Underserved / 🟡 Balanced / 🟢 Well-served

#### Section 2 — Cuisine Breakdown (Bar Chart)
Recharts `BarChart`, horizontal bars, one bar per cuisine sub-type in selected suburb.
```
South Indian   ████████  4
North Indian   ██████    3
Sri Lankan     ██        1
Other          ████      2
```
Colour matches dot colours from Layer 2.

#### Section 3 — Top Restaurants Table
Simple table: Name | Cuisine | Rating | Reviews
Sorted by `demand_score` descending.
Max 8 rows, scrollable.

#### Section 4 — Suburb Comparison (Scatter Plot)
Recharts `ScatterChart`:
- X-axis: Indian population % (demand proxy)
- Y-axis: Restaurant count per 10k Indian residents (supply)
- Each dot = one SA2 suburb
- Selected suburb highlighted in amber
- Quadrant lines at median X and median Y
- Quadrant labels: "High Demand / Low Supply" (opportunity), etc.

This chart alone tells the whole business story at a glance.

#### Section 5 — Income × Supply Bubble Chart
Recharts `ScatterChart`:
- X-axis: Median household income
- Y-axis: Indian restaurant count
- Bubble size: Total Indian-born population
- Colour: `gap_score`
Helps identify premium opportunity zones (high income + high Indian pop + low supply).

---

### Filter Panel (Right Side, Collapsible)
- Position: Right edge, `260px` wide
- Background: same as left panel

**Filter controls:**

| Control | Type | Options |
|---|---|---|
| Cuisine sub-type | Multi-select checkboxes | South Indian, North Indian, Sri Lankan, Bangladeshi, All |
| Chain vs independent | Toggle | Independent only / All |
| Minimum reviews | Slider | 0 – 500+ |
| Minimum rating | Star selector | 1–5 |
| Income bracket | Range slider | $40k – $150k+ |
| Show opportunity gaps only | Toggle | On/Off |

All filters update all layers simultaneously with smooth transitions.

---

### Tooltip Design
Shown on hover over any restaurant dot or suburb polygon.

**Restaurant tooltip:**
```
┌─────────────────────────────┐
│ 🍛 Dosa Corner              │
│ South Indian Restaurant     │
│ ★ 4.6  (312 reviews)        │
│ 45 Church St, Dandenong     │
│ Chain: No                   │
└─────────────────────────────┘
```
- Background: `#1F2937` with 1px `#374151` border
- Radius: 8px
- Font: Inter or system-ui
- Positioned using Floating UI to avoid viewport overflow

**Suburb tooltip (on polygon hover):**
```
┌─────────────────────────────┐
│ Dandenong                   │
│ Indian population: 18.4%    │
│ Indian restaurants: 12      │
│ Median income: $72,400      │
│ Gap score: ██ Underserved   │
└─────────────────────────────┘
```

---

### Legend (Bottom Left)
Compact, always visible.
- Choropleth scale: gradient bar, `0%` to `20%+` Indian population
- Restaurant dot legend: 4 colour swatches + labels
- Hex layer scale: gradient bar, `Oversupplied` to `High Opportunity`
- Gap score explanation: one-line note

---

### Loading & Empty States
- Initial load: full-screen skeleton with animated pulsing dark shapes simulating the map panels
- No data for suburb: "No Indian restaurant data available for this area"
- Error state: Inline error badge with retry button

---

## Interactions & Behaviour

| Trigger | Behaviour |
|---|---|
| Click suburb polygon | Fly-to suburb, open left panel with suburb data |
| Hover restaurant dot | Show tooltip |
| Click restaurant dot | Expand tooltip to full card with all attributes |
| Toggle layer buttons | Smooth opacity fade in/out (300ms) |
| Apply filter | All visible layers re-render in 200ms |
| Drag map | Normal pan/zoom, tooltips dismiss |
| Pinch/scroll zoom | Standard Mapbox zoom |
| Click "Reset" | Fly back to Melbourne overview, clear filters, close panels |
| Press `Escape` | Close all panels, clear selection |

---

## Derived Intelligence Outputs

These are computed in-browser from the joined datasets and surfaced in the side panel:

### Opportunity Score (per SA2)
```
opportunity_score = (
  (india_pct / max_india_pct) * 0.4 +
  (median_income / max_income) * 0.2 +
  ((1 - supply_density / max_supply_density) * 0.4)
)
```
Score range: 0.0 – 1.0. Displayed as a gauge or bar in the suburb summary card.

### Whitespace Alert
Automatically surface top 5 suburbs with:
- `india_pct > 10%`
- `restaurant_count < 3`
- `median_income > $65,000`

Shown as a "Top Opportunities" list in the left panel, always visible regardless of suburb selection.

---

## File Structure

```
/
├── public/
│   ├── data/
│   │   ├── foursquare_melbourne_indian.geojson
│   │   ├── abs_sa2_indian_population.geojson   (SA2 polygons + attributes)
│   │   ├── google_places_demand.json
│   │   └── clue_restaurants.json
├── src/
│   ├── components/
│   │   ├── Map.jsx                  (DeckGL + Mapbox wrapper)
│   │   ├── LayerControls.jsx        (top nav toggles)
│   │   ├── SidePanel.jsx            (left panel, accordion)
│   │   ├── FilterPanel.jsx          (right panel)
│   │   ├── Tooltip.jsx              (floating tooltip)
│   │   ├── Legend.jsx               (bottom-left legend)
│   │   ├── charts/
│   │   │   ├── CuisineBar.jsx
│   │   │   ├── OpportunityScatter.jsx
│   │   │   └── IncomeBubble.jsx
│   ├── layers/
│   │   ├── choroplethLayer.js
│   │   ├── restaurantLayer.js
│   │   ├── heatmapLayer.js
│   │   ├── hexagonLayer.js
│   │   └── clueLayer.js
│   ├── hooks/
│   │   ├── useMapData.js
│   │   ├── useFilters.js
│   │   └── useOpportunityScore.js
│   ├── utils/
│   │   ├── colorScales.js           (d3 colour maps)
│   │   ├── opportunityScore.js      (derived metric computation)
│   │   └── h3Utils.js               (H3 hexbin aggregation)
│   └── App.jsx
```

---

## Data Pipeline (Pre-processing, run once)

A small Python script prepares the static data files before the app is deployed.

```
scripts/
└── prepare_data.py
    Steps:
    1. Load Foursquare Parquet → filter bbox Melbourne → filter Indian cuisine categories → export GeoJSON
    2. Load ABS SA2 boundaries GeoJSON → join with ABS Census CSV (country of birth) → compute india_pct → export merged GeoJSON
    3. Call Google Places API for each suburb centroid → aggregate results → export JSON
    4. Load CLUE CSV → filter for restaurant ANZSIC codes → filter by name keywords (Indian, curry, dosa, etc.) → export JSON
    5. Compute gap_score per SA2 → append to SA2 GeoJSON
```

---

## Performance Considerations

- All GeoJSON data should be pre-simplified to Douglas-Peucker tolerance ~50m (use `mapshaper`)
- SA2 boundaries: expected ~800 polygons for Greater Melbourne — fine for GPU rendering
- Foursquare restaurants: expected ~300–500 points — trivial
- Google Places: ~500 results — trivial
- H3 hexbin aggregation runs client-side in a Web Worker to avoid blocking the main thread
- Use `useMemo` to memoise layer objects and avoid unnecessary Deck.gl re-renders on unrelated state changes

---

## Deployment

- Static site (no backend) — deployable to **Vercel**, **Netlify**, or **Cloudflare Pages** for free
- Mapbox token: environment variable (`VITE_MAPBOX_TOKEN`)
- Google Places key: environment variable, calls proxied through a Cloudflare Worker to hide key (optional for prototype)
- Total bundle size target: < 1.5MB gzipped

---

## MVP Scope (Phase 1)

For a first working version, implement only:
1. SA2 choropleth (Layer 1)
2. Restaurant scatter points (Layer 2)
3. Suburb click → left panel summary card
4. Cuisine filter checkboxes
5. Basic tooltip on restaurant hover

All other layers and charts are Phase 2 enhancements.

---

## Nice-to-Have (Phase 3)

- Time-lapse animation of CLUE restaurant data 2002–2023 showing emergence of Indian cuisine across Melbourne
- Export selected suburb report as PDF
- "Find me a location" mode: user inputs parameters (budget, cuisine type, target demographic), system surfaces top 3 suburb recommendations with scores
- Malayalam / Hindi language toggle for restaurant names where available
