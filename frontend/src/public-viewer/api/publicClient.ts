// Public reader API client. Read-only, unauthenticated, and pointed at the
// backend's /public surface (NOT the private /api). It never sends or reads an
// auth token.

const PUBLIC_API_BASE =
  (import.meta.env.VITE_PUBLIC_API_BASE as string | undefined) ?? '/public';

export class PublicApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'PublicApiError';
  }
}

export async function publicFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${PUBLIC_API_BASE}${path}`, {
    headers: { Accept: 'application/json' },
  });

  const contentType = response.headers.get('content-type') ?? '';
  const body = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new PublicApiError(detail, response.status);
  }

  return body as T;
}

/**
 * Resolve a stored media path to a loadable URL. Demo/public paths begin with
 * `/public/...` and resolve through the same proxy that serves the API, so
 * they are returned unchanged. Absolute http(s) URLs pass through too.
 */
export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  if (/^https?:\/\//i.test(path) || path.startsWith('/')) return path;
  return `${PUBLIC_API_BASE}/${path}`;
}
