'use client'

import { useEffect, useState, useMemo, useCallback } from 'react'

const MAX_VISIBLE = 55
const HANDOVER_YEARS = ['', '2026', '2027', '2028', '2029', '2030', '2031', '2032', 'ready'] as const
const SORT_OPTIONS = ['', 'recent', 'late'] as const

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
  const priceStr = p.price_display || formatPrice(p)
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
          View on 99acres →
        </a>
      )}
    </article>
  )
}

export default function Home() {
  const [properties, setProperties] = useState<Property[]>([])
  const [loading, setLoading] = useState(true)
  const [dark, setDark] = useState(false)
  const [priceMin, setPriceMin] = useState<string>('')
  const [priceMax, setPriceMax] = useState<string>('')
  const [handoverYear, setHandoverYear] = useState<string>('')
  const [status, setStatus] = useState<string>('')
  const [locality, setLocality] = useState<string>('')
  const [builder, setBuilder] = useState<string>('')
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
    let list = properties.filter((p) => {
      const pm = parseFloat(priceMin) || null
      const px = parseFloat(priceMax) || null
      if (pm != null) {
        const maxP = p.price_max_lakhs ?? p.price_min_lakhs
        if (maxP == null || maxP < pm) return false
      }
      if (px != null) {
        const minP = p.price_min_lakhs ?? p.price_max_lakhs
        if (minP == null || minP > px) return false
      }
      if (handoverYear === 'ready') {
        if (!p.handover || !String(p.handover).toLowerCase().includes('ready')) return false
      } else if (handoverYear) {
        const y = p.handover_year
        if (y == null || y !== parseInt(handoverYear, 10)) return false
      }
      if (status && (p.status || '') !== status) return false
      const loc = locality.trim().toLowerCase()
      if (loc && !(p.locality || '').toLowerCase().includes(loc)) return false
      const bld = builder.trim().toLowerCase()
      if (bld && !(p.builder || '').toLowerCase().includes(bld)) return false
      return true
    })
    return sortByHandover(list, sortHandover)
  }, [properties, priceMin, priceMax, handoverYear, status, locality, builder, sortHandover])

  const resetFilters = useCallback(() => {
    setPriceMin('')
    setPriceMax('')
    setHandoverYear('')
    setStatus('')
    setLocality('')
    setBuilder('')
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
          <>
            <div className="loadMsg">
              {properties.length
                ? `Loaded ${properties.length} properties. Use filters and sort below.`
                : 'No properties. Run the scraper to generate public/properties.json.'}
            </div>
            <div className="filters">
              <div className="filterGroup">
                <label>Price min (Lakhs)</label>
                <input
                  type="number"
                  placeholder="e.g. 50"
                  min={0}
                  step={10}
                  value={priceMin}
                  onChange={(e) => setPriceMin(e.target.value)}
                />
              </div>
              <div className="filterGroup">
                <label>Price max (Lakhs)</label>
                <input
                  type="number"
                  placeholder="e.g. 300"
                  min={0}
                  step={10}
                  value={priceMax}
                  onChange={(e) => setPriceMax(e.target.value)}
                />
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
              <div className="filterActions">
                <span className="count">
                  {properties.length === 0
                    ? 'No data'
                    : `Showing ${filtered.length} of ${properties.length} properties`}
                </span>
                <button type="button" className="btn btnSecondary" onClick={resetFilters}>
                  Reset
                </button>
              </div>
            </div>
            <div className="cards">
              {filtered.length === 0 ? (
                <p className="empty">No properties match the filters.</p>
              ) : (
                filtered.map((p) => (
                  <PropertyCard key={p.id || p.name || Math.random()} p={p} />
                ))
              )}
            </div>
          </>
        )}
      </main>
    </>
  )
}
