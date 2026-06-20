import { redirect } from "next/navigation";

// 设计 §7：用户管理替代原白名单管理。保留此路径以兼容旧书签/外链，直接重定向到用户管理。
export default function AdminWhitelistRedirectPage() {
  redirect("/admin/users");
}
