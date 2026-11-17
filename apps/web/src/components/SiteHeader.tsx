import Image from "next/image";
import Link from "next/link";
import { LogoutButton } from "@/components/LogoutButton";
import { PRODUCT_NAME } from "@/lib/brand";
import type { Session } from "@/lib/session";

export function SiteHeader({
  who = null,
  logout,
  demo = false,
}: {
  who?: Session | null;
  logout?: () => void | Promise<void>;
  demo?: boolean;
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-5">
      <Link href="/" className="flex items-center gap-3">
        <Image src="/logo.png" alt="" width={40} height={40} className="rounded-xl" priority />
        <span className="font-display text-2xl">{PRODUCT_NAME}</span>
      </Link>
      <div className="flex items-center gap-4 text-sm text-muted">
        {demo ? (
          <span className="rounded-full border border-accent/50 px-3 py-1 text-accent">
            Demo with sample data
          </span>
        ) : null}
        {who ? (
          <span>
            Signed in as {who.username} ({who.role})
          </span>
        ) : null}
        {logout ? <LogoutButton action={logout} /> : null}
      </div>
    </header>
  );
}
