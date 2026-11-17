import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

// Every page requires a valid session cookie except the login page. Not configured = locked.
export async function proxy(request: NextRequest) {
  if (request.nextUrl.pathname === "/login") return NextResponse.next();
  const valid = await verifySession(
    request.cookies.get(SESSION_COOKIE)?.value,
    process.env.LYVERN_SESSION_SECRET,
  );
  if (valid) return NextResponse.next();
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
