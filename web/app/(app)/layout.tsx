import Link from "next/link";
import { requireUser } from "@/lib/auth";
import { signOut } from "./actions";

export default async function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const { user } = await requireUser();

  return (
    <div className="shell">
      <header className="topbar">
        <Link className="brand" href="/latest">Neurofeed</Link>
        <nav className="nav" aria-label="Primary navigation">
          <Link href="/latest">Latest</Link>
          <Link href="/history">History</Link>
          <Link href="/saved">Saved</Link>
          <Link href="/settings">Settings</Link>
          <form action={signOut}><button className="secondary" type="submit">Sign out</button></form>
        </nav>
      </header>
      <main>
        <p className="muted" style={{ marginTop: "-1rem" }}>{user.email}</p>
        {children}
      </main>
    </div>
  );
}
