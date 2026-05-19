import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const targetUrl = searchParams.get('url');

    if (!targetUrl) {
      return new NextResponse('Missing url parameter', { status: 400 });
    }

    // Fetch the file from Terabox
    const response = await fetch(targetUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
      }
    });

    if (!response.ok) {
      return new NextResponse(`Failed to fetch from source: ${response.status}`, { status: response.status });
    }

    // Get the content type and length
    const contentType = response.headers.get('content-type') || 'application/octet-stream';
    const contentLength = response.headers.get('content-length');

    const headers = new Headers();
    headers.set('Content-Type', contentType);
    if (contentLength) {
      headers.set('Content-Length', contentLength);
    }
    
    // Force download header
    headers.set('Content-Disposition', 'attachment; filename="video.mp4"');

    // Return the readable stream directly to the client
    return new NextResponse(response.body, {
      status: 200,
      headers
    });

  } catch (error: any) {
    console.error('Streaming error:', error.message);
    return new NextResponse('Internal Server Error', { status: 500 });
  }
}
