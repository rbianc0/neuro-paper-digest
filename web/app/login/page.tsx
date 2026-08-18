import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { sendMagicLink } from "./actions";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ sent?: string; error?: string }> }) {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (user) redirect("/latest");
  const params = await searchParams;

  return (
    <main className="shell">
      <div className="form-card">
        <div className="kicker">Neurofeed</div>
        <h1>Sign in</h1>
        <p className="muted">Use a magic link. No password is required.</p>
        {params.sent ? <p className="notice">Check your inbox for the sign-in link.</p> : null}
        {params.error ? <p className="error">{params.error}</p> : null}
        <form action={sendMagicLink} className="form-grid">
          <label>
            Email
            <input name="email" type="email" autoComplete="email" required />
          </label>
          <button type="submit">Send magic link</button>
        </form>
      </div>
    </main>
  );
}
