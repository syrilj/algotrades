import { redirect } from "next/navigation";

/** Legacy path — landing now lives at `/`. */
export default function WelcomeRedirectPage() {
  redirect("/");
}
