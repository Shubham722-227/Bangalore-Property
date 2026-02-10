import Database from 'better-sqlite3'
import path from 'path'

const DB_PATH = path.join(process.cwd(), 'data', 'banglprop.db')

let db: Database.Database | null = null

export function getDb(): Database.Database | null {
  if (db) return db
  try {
    db = new Database(DB_PATH, { readonly: true })
    db.pragma('journal_mode = WAL')
    return db
  } catch {
    return null
  }
}

export type PropertyRow = {
  url: string
  id: string | null
  source: string | null
  status: string | null
  name: string | null
  builder: string | null
  locality: string | null
  price_min_lakhs: number | null
  price_max_lakhs: number | null
  price_display: string | null
  handover: string | null
  handover_year: number | null
  bhk: string | null
}

export type AuctionRow = {
  url: string
  id: string | null
  name: string | null
  description: string | null
  price_display: string | null
  price_lakhs: number | null
  emd_display: string | null
  emd_lakhs: number | null
  sq_ft: string | null
  bank_name: string | null
  branch_name: string | null
  contact: string | null
  contact_person: string | null
  contact_mobile: string | null
  address: string | null
  auction_start: string | null
  auction_end: string | null
  auction_datetime: string | null
  category: string | null
  source: string | null
}

export type PropertiesQuery = {
  page?: number
  limit?: number
  priceMin?: number
  priceMax?: number
  handoverYear?: string
  status?: string
  locality?: string
  builder?: string
  source?: string
  sort?: string
}

export type AuctionsQuery = {
  page?: number
  limit?: number
  priceMin?: number
  priceMax?: number
  bank?: string
  category?: string
  locality?: string
}

function toPropertyRecord(row: PropertyRow) {
  return {
    id: row.id ?? undefined,
    source: row.source ?? undefined,
    status: row.status ?? undefined,
    name: row.name ?? undefined,
    builder: row.builder ?? undefined,
    locality: row.locality ?? undefined,
    price_min_lakhs: row.price_min_lakhs ?? undefined,
    price_max_lakhs: row.price_max_lakhs ?? undefined,
    price_display: row.price_display ?? undefined,
    handover: row.handover ?? undefined,
    handover_year: row.handover_year ?? undefined,
    bhk: row.bhk ?? undefined,
    url: row.url ?? undefined,
  }
}

function toAuctionRecord(row: AuctionRow) {
  return {
    id: row.id ?? undefined,
    name: row.name ?? undefined,
    description: row.description ?? undefined,
    price_display: row.price_display ?? undefined,
    price_lakhs: row.price_lakhs ?? undefined,
    emd_display: row.emd_display ?? undefined,
    emd_lakhs: row.emd_lakhs ?? undefined,
    sq_ft: row.sq_ft ?? undefined,
    bank_name: row.bank_name ?? undefined,
    branch_name: row.branch_name ?? undefined,
    contact: row.contact ?? undefined,
    contact_person: row.contact_person ?? undefined,
    contact_mobile: row.contact_mobile ?? undefined,
    address: row.address ?? undefined,
    url: row.url ?? undefined,
    auction_start: row.auction_start ?? undefined,
    auction_end: row.auction_end ?? undefined,
    auction_datetime: row.auction_datetime ?? undefined,
    category: row.category ?? undefined,
    source: row.source ?? undefined,
  }
}

export function queryProperties(q: PropertiesQuery): { data: ReturnType<typeof toPropertyRecord>[]; total: number } {
  const database = getDb()
  if (!database) return { data: [], total: 0 }
  const page = Math.max(1, q.page ?? 1)
  const limit = Math.min(100, Math.max(1, q.limit ?? 24))
  const offset = (page - 1) * limit
  const conditions: string[] = ["1=1"]
  const params: (string | number)[] = []
  if (q.priceMin != null && q.priceMin > 0) {
    conditions.push("(price_max_lakhs IS NULL OR price_max_lakhs >= ?)")
    params.push(q.priceMin)
  }
  if (q.priceMax != null && q.priceMax < 1000) {
    conditions.push("(price_min_lakhs IS NULL OR price_min_lakhs <= ?)")
    params.push(q.priceMax)
  }
  if (q.handoverYear === 'ready') {
    conditions.push("(handover IS NOT NULL AND LOWER(handover) LIKE '%ready%')")
  } else if (q.handoverYear) {
    const y = parseInt(q.handoverYear, 10)
    if (!isNaN(y)) { conditions.push("handover_year = ?"); params.push(y) }
  }
  if (q.status) { conditions.push("status = ?"); params.push(q.status) }
  if (q.locality?.trim()) { conditions.push("(LOWER(locality) LIKE ?)"); params.push('%' + q.locality.trim().toLowerCase() + '%') }
  if (q.builder?.trim()) { conditions.push("(LOWER(builder) LIKE ?)"); params.push('%' + q.builder.trim().toLowerCase() + '%') }
  if (q.source) { conditions.push("source = ?"); params.push(q.source) }
  const where = conditions.join(' AND ')
  const priceFirst = "CASE WHEN price_min_lakhs IS NOT NULL OR price_max_lakhs IS NOT NULL THEN 0 ELSE 1 END"
  const order =
    q.sort === 'recent'
      ? `ORDER BY ${priceFirst}, CASE WHEN handover IS NOT NULL AND LOWER(handover) LIKE '%ready%' THEN -1 ELSE COALESCE(handover_year, 9999) END ASC`
      : q.sort === 'late'
        ? `ORDER BY ${priceFirst}, CASE WHEN handover IS NOT NULL AND LOWER(handover) LIKE '%ready%' THEN 0 ELSE COALESCE(handover_year, -9999) END DESC`
        : `ORDER BY ${priceFirst}, updated_at DESC`
  const countSql = `SELECT COUNT(*) AS total FROM properties WHERE ${where}`
  const countStmt = database.prepare(countSql)
  const total = (countStmt.get(...params) as { total: number }).total
  const dataSql = `SELECT url, id, source, status, name, builder, locality, price_min_lakhs, price_max_lakhs, price_display, handover, handover_year, bhk FROM properties WHERE ${where} ${order} LIMIT ? OFFSET ?`
  const dataStmt = database.prepare(dataSql)
  const rows = dataStmt.all(...params, limit, offset) as PropertyRow[]
  return { data: rows.map(toPropertyRecord), total }
}

export function queryAuctions(q: AuctionsQuery): { data: ReturnType<typeof toAuctionRecord>[]; total: number } {
  const database = getDb()
  if (!database) return { data: [], total: 0 }
  const page = Math.max(1, q.page ?? 1)
  const limit = Math.min(100, Math.max(1, q.limit ?? 24))
  const offset = (page - 1) * limit
  const conditions: string[] = ["1=1"]
  const params: (string | number)[] = []
  if (q.priceMin != null && q.priceMin > 0) {
    conditions.push("(price_lakhs IS NOT NULL AND price_lakhs >= ?)")
    params.push(q.priceMin)
  }
  if (q.priceMax != null && q.priceMax < 1000) {
    conditions.push("(price_lakhs IS NOT NULL AND price_lakhs <= ?)")
    params.push(q.priceMax)
  }
  if (q.bank?.trim()) { conditions.push("(LOWER(bank_name) LIKE ?)"); params.push('%' + q.bank.trim().toLowerCase() + '%') }
  if (q.category?.trim()) { conditions.push("LOWER(TRIM(category)) = ?"); params.push(q.category.trim().toLowerCase()) }
  if (q.locality?.trim()) {
    const loc = '%' + q.locality.trim().toLowerCase() + '%'
    conditions.push("(LOWER(COALESCE(address,'')) LIKE ? OR LOWER(COALESCE(name,'')) LIKE ?)")
    params.push(loc, loc)
  }
  const where = conditions.join(' AND ')
  const countSql = `SELECT COUNT(*) AS total FROM auctions WHERE ${where}`
  const countStmt = database.prepare(countSql)
  const total = (countStmt.get(...params) as { total: number }).total
  const dataSql = `SELECT url, id, name, description, price_display, price_lakhs, emd_display, emd_lakhs, sq_ft, bank_name, branch_name, contact, contact_person, contact_mobile, address, auction_start, auction_end, auction_datetime, category, source FROM auctions WHERE ${where} ORDER BY updated_at DESC LIMIT ? OFFSET ?`
  const dataStmt = database.prepare(dataSql)
  const rows = dataStmt.all(...params, limit, offset) as AuctionRow[]
  return { data: rows.map(toAuctionRecord), total }
}
