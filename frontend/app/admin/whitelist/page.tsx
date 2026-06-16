import { redirect } from "next/navigation";

export default function AdminWhitelistRedirectPage() {
  redirect("/admin/users");
}
