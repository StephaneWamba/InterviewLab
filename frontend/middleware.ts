import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Public routes that don't require authentication
  const publicRoutes = ['/login', '/register'];
  const isPublicRoute = publicRoutes.includes(pathname);

  // Protected routes
  const isProtectedRoute = pathname.startsWith('/dashboard');

  // For protected routes, we'll handle auth client-side
  // This middleware just ensures proper routing
  if (isProtectedRoute) {
    // Client-side will handle redirect if not authenticated
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};

