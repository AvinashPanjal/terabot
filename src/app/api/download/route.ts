import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  try {
    const { url } = await request.json();

    if (!url) {
      return NextResponse.json({ error: 'URL is required' }, { status: 400 });
    }

    // Call the robust local Python FastAPI microservice that bypasses Cloudflare
    // Using 127.0.0.1 instead of localhost to prevent IPv6 resolution errors in Node's native fetch
    const apiEndpoint = process.env.TERABOX_API_ENDPOINT || 'http://127.0.0.1:8000/api/extract';

    const response = await fetch(apiEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url }),
    });

    if (!response.ok) {
      throw new Error(`Python Microservice responded with status: ${response.status}`);
    }

    const data = await response.json();

    if (!data.success || !data.directUrl) {
      return NextResponse.json({ error: 'Could not extract direct download URL from TeraBox link.' }, { status: 404 });
    }

    return NextResponse.json({
      success: true,
      directUrl: data.directUrl,
      filename: data.filename || 'video.mp4',
    });

  } catch (error: any) {
    console.error('Terabox Download API Error:', error.message);
    return NextResponse.json({ error: error.message || 'Internal Server Error' }, { status: 500 });
  }
}
