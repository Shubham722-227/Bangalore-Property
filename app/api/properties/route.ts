import { NextRequest, NextResponse } from 'next/server'
import { queryProperties } from '@/lib/db'

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
      handoverYear: searchParams.get('handoverYear') ?? undefined,
      status: searchParams.get('status') ?? undefined,
      locality: searchParams.get('locality') ?? undefined,
      builder: searchParams.get('builder') ?? undefined,
      source: searchParams.get('source') ?? undefined,
      sort: searchParams.get('sort') ?? undefined,
    }
    const result = queryProperties(query)
    return NextResponse.json({
      data: result.data,
      total: result.total,
      page,
      limit,
    })
  } catch (e) {
    console.error('API properties error:', e)
    return NextResponse.json({ error: 'Server error', data: [], total: 0, page: 1, limit: 24 }, { status: 500 })
  }
}
