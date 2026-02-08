'use client'

import { useEffect, useState, useMemo, useCallback } from 'react'

const MAX_VISIBLE = 55
const PRICE_SLIDER_MAX = 1000 // lakhs (10 Cr)
const HANDOVER_YEARS = ['', '2026', '2027', '2028', '2029', '2030', '2031', '2032', 'ready'] as const
const JUNK_NAMES = new Set([
  'new launch projects in bangalore', 'under construction projects in bangalore',
  'ready to move projects in bangalore', 'new projects in bangalore', 'projects in bangalore',
  'upcoming projects in bangalore', 'new projects by reputed bangalore builders in bangalore',
  'ready to move & pre launch', 'list', 'map', 'filter your search', 'reset', 'sort by',
  'find other projects matching your search nearby', 'quick links', 'bangalore',
])
const SORT_OPTIONS = ['', 'recent', 'late'] as const

function formatPriceLabel(lakhs: number): string {
  if (lakhs >= 100) return `${(lakhs / 100).toFixed(1)} Cr`
  return `${lakhs} L`
}

type Property = {
  id?: string
  source?: string
  status?: string
  name?: string
  builder?: string
  locality?: string
  price_min_lakhs?: number | null
  price_max_lakhs?: number | null
  price_display?: string
  handover?: string
  handover_year?: number | null
  bhk?: string
  url?: string
}

function formatPrice(p: Property): string {
  const min = p.price_min_lakhs ?? p.price_max_lakhs
  const max = p.price_max_lakhs ?? p.price_min_lakhs
  if (min == null && max == null) return ''
  const mn = min ?? max ?? 0
  const mx = max ?? min ?? 0
  if (mx >= 100) return `₹ ${(mn / 100).toFixed(2)} - ${(mx / 100).toFixed(2)} Cr`
  return `₹ ${mn} - ${mx} L`
}

function sortByHandover(list: Property[], order: string): Property[] {
  if (!order) return list
  const ready = (p: Property) => String(p.handover || '').toLowerCase().includes('ready')
  const year = (p: Property) => {
    if (p.handover_year != null) return p.handover_year
    if (ready(p)) return order === 'recent' ? -1 : 0
    return order === 'recent' ? 9999 : -9999
  }
  return [...list].sort((a, b) => (order === 'recent' ? year(a) - year(b) : year(b) - year(a)))
}

function ReadMoreText({
  text,
  label,
  className = '',
}: {
  text: string
  label?: string
  className?: string
}) {
  const [expanded, setExpanded] = useState(false)
  if (!text) return null
  const short = text.length <= MAX_VISIBLE
  if (short) {
    return <span className={className}>{label ? `${label} ${text}` : text}</span>
  }
  const shortText = text.slice(0, MAX_VISIBLE).trim() + '…'
  return (
    <span className={className}>
      {label && `${label} `}
      <span className={`textWrap ${expanded ? 'expanded' : ''}`}>
        <span className="short">{shortText}</span>
        <span className="full">{text}</span>
        <button
          type="button"
          className="readMore"
          onClick={() => setExpanded((e) => !e)}
        >
          {expanded ? 'Read less' : 'Read more'}
        </button>
      </span>
    </span>
  )
}

function PropertyCard({ p }: { p: Property }) {
  const hasNumericPrice = p.price_min_lakhs != null || p.price_max_lakhs != null
  const priceStr = hasNumericPrice ? (p.price_display || formatPrice(p)) : (p.price_display && p.price_display !== 'Price on Demand' ? p.price_display : 'Contact for price')
  const statusLabel = (p.status || '').replace(/_/g, ' ')
  const statusClass =
    p.status === 'new_launch'
      ? 'statusNewLaunch'
      : p.status === 'under_construction'
        ? 'statusUnderConstruction'
        : p.status === 'ready_to_move'
          ? 'statusReadyToMove'
          : ''

  return (
    <article className="card">
      <div className="cardName">
        <ReadMoreText text={p.name || ''} />
      </div>
      {p.builder && <div className="cardBuilder">{p.builder}</div>}
      {p.locality && (
        <div className="cardLocality">
          <ReadMoreText text={p.locality} />
        </div>
      )}
      <div className="cardPrice">{priceStr}</div>
      <div className="cardMeta">
        <span className={statusClass}>{statusLabel}</span>
        {p.handover && <span>{p.handover}</span>}
        {p.bhk && <span>{p.bhk} BHK</span>}
      </div>
      {p.url && (
        <a className="cardLink" href={p.url} target="_blank" rel="noopener noreferrer">
          View on {p.source === 'nobroker' ? 'NoBroker' : '99acres'} →
        </a>
      )}
    </article>
  )
}

export default function Home() {
  const [properties, setProperties] = useState<Property[]>([])
  const [loading, setLoading] = useState(true)
  const [dark, setDark] = useState(false)
  const [priceMinLakhs, setPriceMinLakhs] = useState(0)
  const [priceMaxLakhs, setPriceMaxLakhs] = useState(PRICE_SLIDER_MAX)
  const [handoverYear, setHandoverYear] = useState<string>('')
  const [status, setStatus] = useState<string>('')
  const [locality, setLocality] = useState<string>('')
  const [builder, setBuilder] = useState<string>('')
  const [sourceFilter, setSourceFilter] = useState<string>('')
  const [sortHandover, setSortHandover] = useState<string>('')

  useEffect(() => {
    const stored = typeof window !== 'undefined' && localStorage.getItem('theme') === 'dark'
    setDark(stored)
    if (typeof document !== 'undefined') {
      if (stored) document.documentElement.classList.add('dark')
      else document.documentElement.classList.remove('dark')
    }
  }, [])

  const toggleTheme = useCallback(() => {
    setDark((d) => {
      const next = !d
      if (typeof document !== 'undefined') {
        if (next) document.documentElement.classList.add('dark')
        else document.documentElement.classList.remove('dark')
        localStorage.setItem('theme', next ? 'dark' : 'light')
      }
      return next
    })
  }, [])

  useEffect(() => {
    fetch('/properties.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('No file'))))
      .then((data: Property[] | unknown) => {
        setProperties(Array.isArray(data) ? data : [])
      })
      .catch(() => setProperties([]))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const minPrice = Number(priceMinLakhs)
    const maxPrice = Number(priceMaxLakhs)
    let list = properties.filter((p) => {
      // Hide page/section titles (not real project names)
      const name = (p.name || '').trim().toLowerCase().slice(0, 120)
      if (!name || name.length < 4) return false
      if (JUNK_NAMES.has(name)) return false
      if ((name.includes('projects in bangalore') || (name.includes('projects in ') && name.includes('bangalore'))) &&
          (name.startsWith('new ') || name.startsWith('under ') || name.startsWith('ready ') || name.startsWith('upcoming '))) return false
      if (name.includes('by reputed') && name.includes('builders') && name.includes('bangalore')) return false
      // Price: show if property range overlaps [minPrice, maxPrice]
      if (minPrice > 0 || maxPrice < PRICE_SLIDER_MAX) {
        const pMin = p.price_min_lakhs != null ? Number(p.price_min_lakhs) : null
        const pMax = p.price_max_lakhs != null ? Number(p.price_max_lakhs) : null
        if (minPrice > 0 && (pMax == null || pMax < minPrice)) return false
        if (maxPrice < PRICE_SLIDER_MAX && (pMin == null || pMin > maxPrice)) return false
      }
      // Handover year
      if (handoverYear === 'ready') {
        if (!p.handover || !String(p.handover).toLowerCase().includes('ready')) return false
      } else if (handoverYear) {
        const y = p.handover_year != null ? Number(p.handover_year) : null
        const selectedYear = parseInt(handoverYear, 10)
        if (y == null || y !== selectedYear) return false
      }
      // Status
      if (status && (p.status || '').trim() !== status) return false
      // Locality (substring match)
      const loc = locality.trim().toLowerCase()
      if (loc && !(p.locality || '').toLowerCase().includes(loc)) return false
      // Builder (substring match)
      const bld = builder.trim().toLowerCase()
      if (bld && !(p.builder || '').toLowerCase().includes(bld)) return false
      // Source
      if (sourceFilter && (p.source || '').trim() !== sourceFilter) return false
      return true
    })
    return sortByHandover(list, sortHandover)
  }, [properties, priceMinLakhs, priceMaxLakhs, handoverYear, status, locality, builder, sourceFilter, sortHandover])

  const resetFilters = useCallback(() => {
    setPriceMinLakhs(0)
    setPriceMaxLakhs(PRICE_SLIDER_MAX)
    setHandoverYear('')
    setStatus('')
    setLocality('')
    setBuilder('')
    setSourceFilter('')
    setSortHandover('')
  }, [])

  return (
    <>
      <header className="header">
        <div className="headerInner">
          <div>
            <h1 className="title">Bangalore Builder Properties</h1>
            <p className="subtitle">
              Upcoming · Under construction · Ready to move · New launch (2026)
            </p>
          </div>
          <button
            type="button"
            className="themeBtn"
            onClick={toggleTheme}
            aria-label={dark ? 'Switch to light mode' : 'Toggle dark mode'}
          >
            {dark ? '☀️' : '🌙'}
          </button>
        </div>
      </header>
      <main className="main">
        {loading && <div className="loadMsg">Loading data…</div>}
        {!loading && (
          <div className="mainLayout">
            <aside className="sidebar">
              <div className="sidebarTitle">Filters</div>
              <div
                className="filterGroup rangeSliderWrap"
                style={
                  {
                    '--min-pct': `${(priceMinLakhs / PRICE_SLIDER_MAX) * 100}%`,
                    '--max-pct': `${(priceMaxLakhs / PRICE_SLIDER_MAX) * 100}%`,
                  } as React.CSSProperties
                }
              >
                <label className="priceRangeLabel">
                  Price Range
                </label>
                <div className="rangeSliderTrack">
                  <input
                    type="range"
                    min={0}
                    max={priceMaxLakhs}
                    step={25}
                    value={priceMinLakhs}
                    onChange={(e) => setPriceMinLakhs(Number(e.target.value))}
                    className="slider sliderMin"
                    aria-label="Price minimum"
                  />
                  <input
                    type="range"
                    min={priceMinLakhs}
                    max={PRICE_SLIDER_MAX}
                    step={25}
                    value={priceMaxLakhs}
                    onChange={(e) => setPriceMaxLakhs(Number(e.target.value))}
                    className="slider sliderMax"
                    aria-label="Price maximum"
                  />
                </div>
                <div className="priceRangeValues">
                  <span className="priceRangeMin">{formatPriceLabel(priceMinLakhs)}</span>
                  <span className="priceRangeMax">{formatPriceLabel(priceMaxLakhs)}</span>
                </div>
              </div>
              <div className="filterGroup">
                <label>Handover year</label>
                <select
                  value={handoverYear}
                  onChange={(e) => setHandoverYear(e.target.value)}
                >
                  <option value="">Any</option>
                  {HANDOVER_YEARS.filter(Boolean).map((y) => (
                    <option key={y} value={y}>
                      {y === 'ready' ? 'Ready to move' : y}
                    </option>
                  ))}
                </select>
              </div>
              <div className="filterGroup">
                <label>Status</label>
                <select value={status} onChange={(e) => setStatus(e.target.value)}>
                  <option value="">All</option>
                  <option value="new_launch">New launch</option>
                  <option value="under_construction">Under construction</option>
                  <option value="ready_to_move">Ready to move</option>
                </select>
              </div>
              <div className="filterGroup">
                <label>Locality</label>
                <input
                  type="text"
                  placeholder="e.g. Whitefield"
                  value={locality}
                  onChange={(e) => setLocality(e.target.value)}
                />
              </div>
              <div className="filterGroup">
                <label>Builder</label>
                <input
                  type="text"
                  placeholder="e.g. Prestige"
                  value={builder}
                  onChange={(e) => setBuilder(e.target.value)}
                />
              </div>
              <div className="filterGroup">
                <label>Source</label>
                <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
                  <option value="">All</option>
                  <option value="99acres">99acres</option>
                  <option value="nobroker">NoBroker</option>
                </select>
              </div>
              <div className="filterGroup">
                <label>Sort by handover</label>
                <select
                  value={sortHandover}
                  onChange={(e) => setSortHandover(e.target.value)}
                >
                  <option value="">Default</option>
                  <option value="recent">Recent handover first</option>
                  <option value="late">Late handover first</option>
                </select>
              </div>
              <button type="button" className="btn btnSecondary resetBtn" onClick={resetFilters}>
                Reset filters
              </button>
            </aside>
            <div className="content">
              <div className="loadMsg">
                {properties.length === 0
                  ? 'No properties. Run the scraper to generate public/properties.json.'
                  : `Showing ${filtered.length} of ${properties.length} properties`}
              </div>
              <div className="cards">
              {filtered.length === 0 ? (
                <p className="empty">No properties match the filters.</p>
              ) : (
                filtered.map((p, i) => (
                  <PropertyCard key={p.id || p.url || `${p.name}-${i}`} p={p} />
                ))
              )}
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  )
}
