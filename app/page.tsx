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

const IMG_FLAT = 'https://i.pinimg.com/736x/4b/83/d2/4b83d22d91a30f0b92d3e0eeea82666f.jpg'
const IMG_LAND = 'https://i.pinimg.com/736x/c3/e3/be/c3e3beab1eea6d3d65a7254e317cdc27.jpg'

const AUCTION_NAV_JUNK = /\.?\s*(Home|About Us|Property List|States|Faqs|Blog|Contact|Register|Login)(\s|$)/gi
const AUCTION_TRAILING_JUNK = /\s*(Cont|Faq|Stat|Blog|Propert|List|States?)\s*$/gi
const AUCTION_GENERIC_NAME = /^Property\s+\d+$/i

// Scraped boilerplate from eauctionsindia (nav, social, meta) – strip after fetch
const AUCTION_SCRAPE_PREFIX = /^(?:Login\s*×\s*)?(?:Home\s+About\s+Us\s+Property\s+List\s+States\s+Faqs\s+Blog\s+Contact\s+Us\s+Register\s+Login\s*)+/i
const AUCTION_PROPERTY_DETAILS = /Property\s+Details\s*/gi
const AUCTION_ID_BLOCK = /Auction\s+ID\s*:\s*#\s*\d+\s*/gi
const AUCTION_SOCIAL_BLOCK = /Facebook\s+X\s*\(\s*Twitter\s*\)\s+LinkedIn\s+WhatsApp\s+Copy\s+Link\s*/gi
const AUCTION_LEADING_US = /^\s*Us\s+Register\s+Login[\s×]*/i
const AUCTION_TIMES_X = /\s*×\s*/g
const AUCTION_US_REGI = /\s*Us\s+Regi\s*/gi

function cleanAuctionText(s: string | undefined): string {
  if (!s || typeof s !== 'string') return ''
  let t = s
    .replace(AUCTION_SCRAPE_PREFIX, ' ')
    .replace(AUCTION_PROPERTY_DETAILS, ' ')
    .replace(AUCTION_ID_BLOCK, ' ')
    .replace(AUCTION_SOCIAL_BLOCK, ' ')
    .replace(AUCTION_LEADING_US, ' ')
    .replace(AUCTION_US_REGI, ' ')
    .replace(AUCTION_TIMES_X, ' ')
    .replace(AUCTION_NAV_JUNK, ' ')
    .replace(AUCTION_TRAILING_JUNK, '')
    .replace(/\s+/g, ' ')
    .replace(/\s*,\s*$/g, '')
    .trim()
  if (t === 'Us' || t === 'Regi' || t === 'Us Regi' || /^Contact\s+Us\s*Regi?$/i.test(t)) return ''
  return t
}

function cleanAuctionRecord(a: Auction): Auction {
  return {
    ...a,
    name: cleanAuctionText(a.name) || a.name,
    description: cleanAuctionText(a.description) || undefined,
    address: cleanAuctionText(a.address) || undefined,
    bank_name: cleanAuctionText(a.bank_name) || a.bank_name,
    contact: cleanAuctionText(a.contact) || undefined,
  }
}

function auctionBankDisplay(bankName: string | undefined): string {
  if (!bankName) return ''
  const cleaned = cleanAuctionText(bankName)
  const known = /(Axis Bank|SBI|HDFC|ICICI|PNB|BOB|Canara|Union Bank|Bank of Baroda|State Bank|DCB Bank|Ujjivan|PNB Housing|Anand Rathi|IDFC|Kotak|Yes Bank|IndusInd|Federal Bank)/i.exec(cleaned)
  if (known) return known[1]
  const ofIndia = /(Bank\s+of\s+India|of\s+India)/i.exec(cleaned)
  if (ofIndia) return 'Bank of India'
  const beforeAuctions = cleaned.split(/\s+Auctions?\s+for\s+/i)[0].trim()
  if (beforeAuctions.length > 2 && beforeAuctions.length < 40) return beforeAuctions
  return cleaned.slice(0, 35) + (cleaned.length > 35 ? '…' : '')
}

function auctionDisplayName(a: Auction): string {
  const rawName = (a.name || '').trim()
  if (rawName && !AUCTION_GENERIC_NAME.test(rawName) && rawName.length > 15) return cleanAuctionText(rawName)
  const category = a.category || 'Property'
  const bank = cleanAuctionText(a.bank_name || '')
  const addr = cleanAuctionText(a.address || '')
  const localityMatch = bank.match(/(?:in|at)\s+([^,]+),\s*Bengaluru/i) || bank.match(/in\s+([^,]+),\s*Bengaluru/i)
  const locality = localityMatch ? localityMatch[1].trim() : ''
  if (locality) return `${category} in ${locality}, Bengaluru`
  const addrLocality = addr.match(/(?:at|in)\s+([^,]{3,50}),\s*(?:Bangalore|Bengaluru)/i) || addr.match(/^([^,]{5,50}),\s*(?:Bangalore|Bengaluru)/i)
  if (addrLocality) return `${category} in ${addrLocality[1].trim()}, Bengaluru`
  if (bank) {
    const inMatch = bank.match(/(?:Auctions?\s+for\s+)?([^,]+)\s+in\s+([^,]+)/i)
    if (inMatch) return `${inMatch[1].trim()} in ${inMatch[2].trim()}, Bengaluru`
  }
  return `${category} auction, Bengaluru` + (a.id ? ` (#${a.id})` : '')
}

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

const PROPERTY_PRICE_MAX_LAKHS = 50000
const PROPERTY_HANDOVER_YEAR_MIN = 2020
const PROPERTY_HANDOVER_YEAR_MAX = 2040
const VALID_STATUSES = new Set(['new_launch', 'under_construction', 'ready_to_move'])

function cleanPropertyRecord(p: Property): Property {
  if (!p || typeof p !== 'object') return p
  const trim = (s: string | undefined) => (typeof s === 'string' ? s.replace(/\s+/g, ' ').trim() : undefined) || undefined
  let name = trim(p.name)
  let price_min_lakhs = p.price_min_lakhs != null ? Number(p.price_min_lakhs) : null
  let price_max_lakhs = p.price_max_lakhs != null ? Number(p.price_max_lakhs) : null
  if (Number.isNaN(price_min_lakhs)) price_min_lakhs = null
  if (Number.isNaN(price_max_lakhs)) price_max_lakhs = null
  if (price_min_lakhs != null && (price_min_lakhs < 0 || price_min_lakhs > PROPERTY_PRICE_MAX_LAKHS)) price_min_lakhs = null
  if (price_max_lakhs != null && (price_max_lakhs < 0 || price_max_lakhs > PROPERTY_PRICE_MAX_LAKHS)) price_max_lakhs = null
  if (price_min_lakhs != null && price_max_lakhs != null && price_min_lakhs > price_max_lakhs) {
    ;[price_min_lakhs, price_max_lakhs] = [price_max_lakhs, price_min_lakhs]
  }
  const price_display = price_min_lakhs != null || price_max_lakhs != null ? (formatPrice({ ...p, price_min_lakhs, price_max_lakhs }) || undefined) : trim(p.price_display)
  let handover_year = p.handover_year != null ? Number(p.handover_year) : null
  if (Number.isNaN(handover_year) || handover_year! < PROPERTY_HANDOVER_YEAR_MIN || handover_year! > PROPERTY_HANDOVER_YEAR_MAX) handover_year = null
  const status = VALID_STATUSES.has((p.status || '').toLowerCase()) ? (p.status as string) : 'new_launch'
  return {
    ...p,
    id: trim(p.id) || p.id,
    source: trim(p.source) || p.source,
    status,
    name: name || p.name,
    builder: trim(p.builder) || p.builder,
    locality: trim(p.locality) || p.locality,
    price_min_lakhs: price_min_lakhs ?? undefined,
    price_max_lakhs: price_max_lakhs ?? undefined,
    price_display: price_display || undefined,
    handover: trim(p.handover) || p.handover,
    handover_year: handover_year ?? undefined,
    bhk: trim(p.bhk) || p.bhk,
    url: trim(p.url) || p.url,
  }
}

type Auction = {
  id?: string
  name?: string
  description?: string
  price_display?: string
  price_lakhs?: number | null
  emd_display?: string
  emd_lakhs?: number | null
  sq_ft?: string | null
  bank_name?: string
  branch_name?: string
  contact?: string
  contact_person?: string
  contact_mobile?: string
  address?: string
  url?: string
  auction_start?: string
  auction_end?: string
  auction_datetime?: string
  category?: string
  source?: string
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

  const isPlot = (p.name || '').toLowerCase().includes('plot') || (p.locality || '').toLowerCase().includes('plot')
  const isLand = (p.name || '').toLowerCase().includes('land') || (p.locality || '').toLowerCase().includes('land')
  const cardImg = isPlot || isLand ? IMG_LAND : IMG_FLAT
  const badgeClass = statusClass === 'statusNewLaunch' ? 'cardBadgePrimary' : statusClass === 'statusReadyToMove' ? 'cardBadgeSuccess' : statusClass === 'statusUnderConstruction' ? 'cardBadgeAmber' : 'cardBadgeSlate'

  return (
    <article className="card">
      <div className="cardImageWrap">
        <img className="cardImage" src={cardImg} alt={isPlot || isLand ? 'Land or plot' : 'Apartment'} />
        <div className="cardBadges">
          <span className={`cardBadge ${badgeClass}`}>{statusLabel}</span>
          {p.bhk && <span className="cardBadge cardBadgeSlate">{p.bhk} BHK</span>}
        </div>
      </div>
      <div className="cardBody">
        <div>
          <h3 className="cardTitle">
            <ReadMoreText text={p.name || 'Property'} />
          </h3>
          {p.builder && <p className="cardSubtitle">By {p.builder}</p>}
        </div>
        {p.locality && (
          <div className="cardLocRow">
            <span className="material-symbols-outlined">location_on</span>
            <span><ReadMoreText text={p.locality} />{p.locality && !p.locality.toLowerCase().includes('bangalore') ? ', Bangalore' : ''}</span>
          </div>
        )}
        <p className="cardPrice">{priceStr}</p>
        <div className="cardFooter">
          <div>
            <div className="cardFooterLabel">Handover</div>
            <div className="cardFooterValue">{p.handover || '—'}</div>
          </div>
          {p.url && (
            <a className="cardLink" href={p.url} target="_blank" rel="noopener noreferrer">
              View Details
            </a>
          )}
        </div>
      </div>
    </article>
  )
}

function AuctionCard({ a }: { a: Auction }) {
  const displayName = auctionDisplayName(a)
  const bankDisplay = auctionBankDisplay(a.bank_name)
  const priceStr = a.price_display || (a.price_lakhs != null ? (a.price_lakhs >= 100 ? `₹ ${(a.price_lakhs / 100).toFixed(2)} Cr` : `₹ ${a.price_lakhs} L`) : 'Contact for price')
  const auctionWhen = a.auction_datetime || [a.auction_start, a.auction_end].filter(Boolean).join(' – ')
  const addressClean = (a.address || '').trim()
  const descClean = (a.description || '').trim()
  const isLand = (a.category || '').toLowerCase() === 'land' || ((displayName || '').toLowerCase().includes('land') && !(displayName || '').toLowerCase().includes('plot'))
  const isPlot = (displayName || '').toLowerCase().includes('plot') && !(a.category || '').toLowerCase().includes('land')
  const cardImg = isLand || isPlot ? IMG_LAND : IMG_FLAT
  const titleLower = displayName.toLowerCase()
  const addrIsRedundant = addressClean.length < 10 || titleLower.includes(addressClean.slice(0, 25).toLowerCase())
  const showAddress = addressClean && !addrIsRedundant
  const combinedTitleDate = `${displayName} ${auctionWhen}`.toLowerCase()
  const descIsRedundant = !descClean || descClean.length < 25 || combinedTitleDate.includes(descClean.slice(0, 40).toLowerCase())
  const showDesc = descClean && !descIsRedundant
  const showContact = (a.contact || '').trim().length > 5

  return (
    <article className="card cardAuction">
      <div className="cardImageWrap">
        <img className="cardImage" src={cardImg} alt={isLand || isPlot ? 'Land or plot' : 'Apartment'} />
        <div className="cardBadges">
          {a.category && <span className="cardBadge cardBadgePrimary">{a.category}</span>}
          {bankDisplay && <span className="cardBadge cardBadgeSlate">{bankDisplay}</span>}
        </div>
      </div>
      <div className="cardBody">
        <h3 className="cardTitle">{displayName}</h3>
        <div className="cardAuctionMeta">
          {a.sq_ft && <span className="cardAuctionSqft">{a.sq_ft} sq ft</span>}
          {auctionWhen && <span className="cardAuctionDate">{auctionWhen}</span>}
        </div>
        {showAddress && (
          <div className="cardLocRow">
            <span className="material-symbols-outlined">location_on</span>
            <span><ReadMoreText text={addressClean.length > 60 ? addressClean.slice(0, 60) + '…' : addressClean} /></span>
          </div>
        )}
        <div className="cardAuctionPriceRow">
          <span className="cardAuctionPrice">{priceStr}</span>
          {a.emd_display && <span className="cardAuctionEmd">EMD {a.emd_display}</span>}
        </div>
        {showDesc && (
          <div className="cardAuctionLine cardAuctionDesc">
            <ReadMoreText text={descClean} className="cardAuctionText" />
          </div>
        )}
        <div className="cardAuctionFooter">
          {showContact && <span className="cardAuctionContact">{a.contact}</span>}
          {a.url && (
            <a className="cardAuctionLink" href={a.url} target="_blank" rel="noopener noreferrer">
              View Details
            </a>
          )}
        </div>
      </div>
    </article>
  )
}

export default function Home() {
  const [mode, setMode] = useState<'builder' | 'auctions'>('builder')
  const [properties, setProperties] = useState<Property[]>([])
  const [auctions, setAuctions] = useState<Auction[]>([])
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
  const [auctionBank, setAuctionBank] = useState<string>('')
  const [auctionCategory, setAuctionCategory] = useState<string>('')

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
    Promise.all([
      fetch('/properties.json').then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch('/auctions.json').then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]).then(([propData, auctionData]) => {
      setProperties(
        Array.isArray(propData)
          ? propData.map(cleanPropertyRecord).filter((p) => (p.name || '').trim().length >= 3 && (p.url || '').startsWith('http'))
          : []
      )
      setAuctions(Array.isArray(auctionData) ? auctionData.map(cleanAuctionRecord) : [])
    }).finally(() => setLoading(false))
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

  const filteredAuctions = useMemo(() => {
    const minPrice = Number(priceMinLakhs)
    const maxPrice = Number(priceMaxLakhs)
    const bank = auctionBank.trim().toLowerCase()
    const cat = auctionCategory.trim().toLowerCase()
    const loc = locality.trim().toLowerCase()
    return auctions.filter((a) => {
      if (minPrice > 0 || maxPrice < PRICE_SLIDER_MAX) {
        const p = a.price_lakhs != null ? Number(a.price_lakhs) : null
        if (p == null) return maxPrice >= PRICE_SLIDER_MAX && minPrice <= 0
        if (minPrice > 0 && p < minPrice) return false
        if (maxPrice < PRICE_SLIDER_MAX && p > maxPrice) return false
      }
      if (bank && !(a.bank_name || '').toLowerCase().includes(bank)) return false
      if (cat && (a.category || '').toLowerCase() !== cat) return false
      if (loc && !(a.address || '').toLowerCase().includes(loc) && !(a.name || '').toLowerCase().includes(loc)) return false
      return true
    })
  }, [auctions, priceMinLakhs, priceMaxLakhs, auctionBank, auctionCategory, locality])

  const resetFilters = useCallback(() => {
    setPriceMinLakhs(0)
    setPriceMaxLakhs(PRICE_SLIDER_MAX)
    setHandoverYear('')
    setStatus('')
    setLocality('')
    setBuilder('')
    setSourceFilter('')
    setSortHandover('')
    setAuctionBank('')
    setAuctionCategory('')
  }, [])

  const setStatusFromChip = (s: string) => { setStatus(s); }
  const setCategoryFromChip = (c: string) => { setAuctionCategory(c); }

  return (
    <>
      <header className="header">
        <div className="headerInner">
          <div className="headerLeft">
            <div className="headerLogo">
              <div className="headerLogoIcon">
                <span className="material-symbols-outlined">domain</span>
              </div>
              <h1 className="title">
                {mode === 'builder' ? 'Bangalore Builder Properties' : 'Bank Auctions'}
              </h1>
            </div>
            <nav className="headerNav" role="tablist" aria-label="Switch between Properties and Auctions">
              <div className="modeToggle">
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === 'builder'}
                  aria-controls="properties-panel"
                  id="tab-properties"
                  className={`modeToggleBtn ${mode === 'builder' ? 'modeToggleBtnActive' : ''}`}
                  onClick={() => setMode('builder')}
                >
                  <span className="material-symbols-outlined">apartment</span>
                  <span>Properties</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === 'auctions'}
                  aria-controls="auctions-panel"
                  id="tab-auctions"
                  className={`modeToggleBtn ${mode === 'auctions' ? 'modeToggleBtnActive' : ''}`}
                  onClick={() => setMode('auctions')}
                >
                  <span className="material-symbols-outlined">gavel</span>
                  <span>Auction Properties</span>
                </button>
              </div>
            </nav>
          </div>
          <div className="headerRight">
            <div className="headerSearchWrap">
              <span className="material-symbols-outlined">search</span>
              <input
                className="headerSearch"
                type="text"
                placeholder={mode === 'builder' ? 'Search by builder or area...' : 'Search by bank or area...'}
                value={locality}
                onChange={(e) => setLocality(e.target.value)}
              />
            </div>
            <button type="button" className="themeBtn" onClick={toggleTheme} aria-label="Toggle theme">
              <span className="material-symbols-outlined">{dark ? 'light_mode' : 'dark_mode'}</span>
            </button>
          </div>
        </div>
      </header>
      {/* Quick filter chips */}
      <div className="chipsWrap">
        {mode === 'builder' ? (
          <>
            <button type="button" className={`chip ${status === '' ? 'chipPrimary' : 'chipSecondary'}`} onClick={() => setStatusFromChip('')}>All Projects</button>
            <button type="button" className={`chip ${status === 'new_launch' ? 'chipPrimary' : 'chipSecondary'}`} onClick={() => setStatusFromChip('new_launch')}>New Launch (2026)</button>
            <button type="button" className={`chip ${status === 'under_construction' ? 'chipPrimary' : 'chipSecondary'}`} onClick={() => setStatusFromChip('under_construction')}>Under Construction</button>
            <button type="button" className={`chip ${status === 'ready_to_move' ? 'chipPrimary' : 'chipSecondary'}`} onClick={() => setStatusFromChip('ready_to_move')}>Ready to Move</button>
          </>
        ) : (
          <>
            <button type="button" className={`chip ${auctionCategory === '' ? 'chipPrimary' : 'chipSecondary'}`} onClick={() => setCategoryFromChip('')}>All</button>
            <button type="button" className={`chip ${auctionCategory === 'residential' ? 'chipPrimary' : 'chipSecondary'}`} onClick={() => setCategoryFromChip('residential')}>Residential</button>
            <button type="button" className={`chip ${auctionCategory === 'land' ? 'chipPrimary' : 'chipSecondary'}`} onClick={() => setCategoryFromChip('land')}>Land</button>
            <button type="button" className={`chip ${auctionCategory === 'commercial' ? 'chipPrimary' : 'chipSecondary'}`} onClick={() => setCategoryFromChip('commercial')}>Commercial</button>
          </>
        )}
      </div>
      <main className="main">
        {loading && <div className="loadMsg">Loading data…</div>}
        {!loading && (
          <div className="mainLayout" id={mode === 'builder' ? 'properties-panel' : 'auctions-panel'} role="tabpanel" aria-labelledby={mode === 'builder' ? 'tab-properties' : 'tab-auctions'}>
            <aside className="sidebar filter-scrollbar">
              <div className="sidebarHeader">
                <h3 className="sidebarTitle">Filters</h3>
                <button type="button" className="sidebarReset" onClick={resetFilters}>Reset All</button>
              </div>
              <div
                className="filterGroup rangeSliderWrap sidebarSection"
                style={
                  {
                    '--min-pct': `${(priceMinLakhs / PRICE_SLIDER_MAX) * 100}%`,
                    '--max-pct': `${(priceMaxLakhs / PRICE_SLIDER_MAX) * 100}%`,
                  } as React.CSSProperties
                }
              >
                <div className="sidebarSectionTitle">
                  <span className="material-symbols-outlined">payments</span>
                  <span>Price Range</span>
                </div>
                <label className="priceRangeLabel" aria-hidden>
                  Range
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
              <div className="sidebarDivider" />
              <div className="sidebarSection">
                <div className="sidebarSectionTitle">
                  <span className="material-symbols-outlined">map</span>
                  <span>{mode === 'auctions' ? 'Address / area' : 'Locality'}</span>
                </div>
                <div className="filterGroup">
                  <input
                    type="text"
                    placeholder={mode === 'auctions' ? 'e.g. Whitefield, Koramangala' : 'e.g. Whitefield'}
                    value={locality}
                    onChange={(e) => setLocality(e.target.value)}
                    style={{ padding: '0.5rem 0.75rem', fontSize: '0.875rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'var(--surface)', color: 'var(--text)' }}
                  />
                </div>
              </div>
              {mode === 'builder' && (
                <>
                  <div className="sidebarDivider" />
                  <div className="sidebarSection">
                    <div className="sidebarSectionTitle">
                      <span className="material-symbols-outlined">apartment</span>
                      <span>Builder</span>
                    </div>
                    <div className="filterGroup">
                      <input
                        type="text"
                        placeholder="e.g. Prestige"
                        value={builder}
                        onChange={(e) => setBuilder(e.target.value)}
                        style={{ padding: '0.5rem 0.75rem', fontSize: '0.875rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'var(--surface)', color: 'var(--text)' }}
                      />
                    </div>
                  </div>
                  <div className="sidebarDivider" />
                  <div className="sidebarSection">
                    <div className="sidebarSectionTitle">
                      <span className="material-symbols-outlined">calendar_month</span>
                      <span>Handover Year</span>
                    </div>
                  <div className="filterGroup">
                    <select
                      value={handoverYear}
                      onChange={(e) => setHandoverYear(e.target.value)}
                      style={{ padding: '0.5rem 0.75rem', fontSize: '0.875rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'var(--surface)', color: 'var(--text)' }}
                    >
                      <option value="">Any</option>
                      {HANDOVER_YEARS.filter(Boolean).map((y) => (
                        <option key={y} value={y}>
                          {y === 'ready' ? 'Ready to move' : y}
                        </option>
                      ))}
                    </select>
                  </div>
                  </div>
                  <div className="sidebarDivider" />
                  <div className="sidebarSection">
                    <div className="sidebarSectionTitle">
                      <span className="material-symbols-outlined">category</span>
                      <span>Status</span>
                    </div>
                  <div className="filterGroup">
                    <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ padding: '0.5rem 0.75rem', fontSize: '0.875rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'var(--surface)', color: 'var(--text)' }}>
                      <option value="">All</option>
                      <option value="new_launch">New launch</option>
                      <option value="under_construction">Under construction</option>
                      <option value="ready_to_move">Ready to move</option>
                    </select>
                  </div>
                  </div>
                  <div className="sidebarDivider" />
                  <div className="sidebarSection">
                    <div className="sidebarSectionTitle">
                      <span className="material-symbols-outlined">source</span>
                      <span>Source</span>
                    </div>
                  <div className="filterGroup">
                    <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} style={{ padding: '0.5rem 0.75rem', fontSize: '0.875rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'var(--surface)', color: 'var(--text)' }}>
                      <option value="">All</option>
                      <option value="99acres">99acres</option>
                      <option value="nobroker">NoBroker</option>
                    </select>
                  </div>
                  </div>
                  <div className="sidebarDivider" />
                  <div className="sidebarSection">
                    <div className="sidebarSectionTitle">
                      <span className="material-symbols-outlined">sort</span>
                      <span>Sort by handover</span>
                    </div>
                  <div className="filterGroup">
                    <select
                      value={sortHandover}
                      onChange={(e) => setSortHandover(e.target.value)}
                    >
                      <option value="">Default</option>
                      <option value="recent">Recent handover first</option>
                      <option value="late">Late handover first</option>
                    </select>
                  </div>
                  </div>
                </>
              )}
              {mode === 'auctions' && (
                <>
                  <div className="sidebarDivider" />
                  <div className="sidebarSection">
                    <div className="sidebarSectionTitle">
                      <span className="material-symbols-outlined">account_balance</span>
                      <span>Bank</span>
                    </div>
                    <div className="filterGroup">
                      <input
                        type="text"
                        placeholder="e.g. SBI, HDFC"
                        value={auctionBank}
                        onChange={(e) => setAuctionBank(e.target.value)}
                        style={{ padding: '0.5rem 0.75rem', fontSize: '0.875rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'var(--surface)', color: 'var(--text)' }}
                      />
                    </div>
                  </div>
                  <div className="sidebarDivider" />
                  <div className="sidebarSection">
                    <div className="sidebarSectionTitle">
                      <span className="material-symbols-outlined">category</span>
                      <span>Category</span>
                    </div>
                    <div className="filterGroup">
                      <select value={auctionCategory} onChange={(e) => setAuctionCategory(e.target.value)} style={{ padding: '0.5rem 0.75rem', fontSize: '0.875rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'var(--surface)', color: 'var(--text)' }}>
                      <option value="">All</option>
                      <option value="residential">Residential</option>
                      <option value="land">Land</option>
                      <option value="commercial">Commercial</option>
                    </select>
                    </div>
                  </div>
                </>
              )}
            </aside>
            <div className="content">
              {mode === 'builder' && (
                <>
                  <div className="summaryBar">
                    <div>
                      <h2 className="summaryTitle">Bangalore Residential Projects</h2>
                      <p className="summaryCount">
                        {properties.length === 0
                          ? 'No properties. Run the scraper to generate public/properties.json.'
                          : `Showing ${filtered.length} of ${properties.length} properties`}
                      </p>
                    </div>
                    <div className="summarySort">
                      <span className="summarySortLabel">Sort by:</span>
                      <select
                        className="summarySortSelect"
                        value={sortHandover}
                        onChange={(e) => setSortHandover(e.target.value)}
                      >
                        <option value="">Handover Year</option>
                        <option value="recent">Recent handover first</option>
                        <option value="late">Late handover first</option>
                      </select>
                    </div>
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
                </>
              )}
              {mode === 'auctions' && (
                <>
                  <div className="summaryBar">
                    <div>
                      <h2 className="summaryTitle">Bank Auctions (Bengaluru)</h2>
                      <p className="summaryCount">
                        {auctions.length === 0
                          ? 'No auctions. Run scraper/scraper_auctions.py to generate public/auctions.json.'
                          : `Showing ${filteredAuctions.length} of ${auctions.length} auctions`}
                      </p>
                    </div>
                  </div>
                  <div className="cards cardsAuction">
                    {filteredAuctions.length === 0 ? (
                      <p className="empty">No auctions match the filters.</p>
                    ) : (
                      filteredAuctions.map((a, i) => (
                        <AuctionCard key={a.id || a.url || `auction-${i}`} a={a} />
                      ))
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </main>
      <footer className="footer">
        <div className="footerInner">
          <div className="footerLogo">
            <div className="footerLogoIcon">
              <span className="material-symbols-outlined">domain</span>
            </div>
            <p className="footerCopy">© {new Date().getFullYear()} Bangalore Builder Properties</p>
          </div>
        </div>
      </footer>
    </>
  )
}
