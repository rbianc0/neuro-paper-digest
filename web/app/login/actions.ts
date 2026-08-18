"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";

function safeMessage(value: string) {
  return encodeURIComponent(value.slice(0, 240));
}

export async function sendMagicLink(formData: FormData) {
  const email = String(formData.get("email") || "").trim().toLowerCase();
  if (!email || !email.includes("@")) {
    redirect(`/login?error=${safeMessage("Enter a valid email address.")}`);
  }

  const headerStore = await headers();
  const origin = process.env.NEXT_PUBLIC_SITE_URL || `${headerStore.get("x-forwarded-proto") || "https"}://${headerStore.get("host")}`;
  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: `${origin}/auth/confirm`,
      shouldCreateUser: true,
    },
  });

  if (error) {
    redirect(`/login?error=${safeMessage(error.message)}`);
  }
  redirect("/login?sent=1");
}
