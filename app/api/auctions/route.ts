import { NextRequest, NextResponse } from 'next/server'
import { queryAuctions } from '@/lib/db'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const page = Math.max(1, parseInt(searchParams.get('page') ?? '1', 10))
    const limit = Math.min(100, Math.max(1, parseInt(searchParams.get('limit') ?? '24', 10)))
    const priceMin = searchParams.get('priceMin')
    const priceMax = searchParams.get('priceMax')
    const query = {
      page,
      limit,
      priceMin: priceMin !== null && priceMin !== '' ? Number(priceMin) : undefined,
      priceMax: priceMax !== null && priceMax !== '' ? Number(priceMax) : undefined,
      bank: searchParams.get('bank') ?? undefined,
      category: searchParams.get('category') ?? undefined,
      locality: searchParams.get('locality') ?? undefined,
    }
    const result = queryAuctions(query)
    return NextResponse.json({
      data: result.data,
      total: result.total,
      page,
      limit,
    })
  } catch (e) {
    console.error('API auctions error:', e)
    return NextResponse.json({ error: 'Server error', data: [], total: 0, page: 1, limit: 24 }, { status: 500 })
  }
}
