"use client";

import { BookOpenText, FileText, Gauge, Languages, MessageSquareText, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState, type ReactNode } from "react";

import { HanMark } from "@/components/seal";
import { Tooltip } from "@/components/ui/tooltip";
import { API_URL, api, type Health } from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const NAV: { href: string; key: MessageKey; icon: typeof FileText }[] = [
  { href: "/", key: "nav.chat", icon: MessageSquareText },
  { href: "/documents", key: "nav.documents", icon: FileText },
  { href: "/evaluation", key: "nav.eval", icon: Gauge },
];

function ApiStatus() {
  const { t } = useI18n();
  const [health, setHealth] = useState<Health | null | "offline">(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const check = async () => {
      try {
        const h = await api.health();
        if (!alive) return;
        setHealth(h);
        if (!h.models_ready) timer = setTimeout(check, 4000);
      } catch {
        if (!alive) return;
        setHealth("offline");
        timer = setTimeout(check, 5000);
      }
    };
    check();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  if (health === null || (health !== "offline" && health.models_ready)) return null;
  return (
    <div
      role="status"
      className={cn(
        "border-b px-4 py-2 text-[13px]",
        health === "offline" ? "border-seal/30 bg-seal-wash text-seal" : "border-mist bg-celadon-wash text-celadon-deep",
      )}
    >
      {health === "offline" ? t("api.offline") : t("api.warming")}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { t, locale, setLocale } = useI18n();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      <aside className="flex shrink-0 items-center gap-1 border-b border-mist bg-surface px-3 py-2 md:sticky md:top-0 md:h-dvh md:w-[76px] md:flex-col md:border-b-0 md:border-r md:px-0 md:py-4">
        <Link href="/" className="mr-2 flex items-center gap-2 md:mb-6 md:mr-0" aria-label="HanRAG">
          <HanMark />
          <span className="font-semibold tracking-tight md:hidden">HanRAG</span>
        </Link>
        <nav className="flex flex-1 items-center gap-1 md:flex-col">
          {NAV.map(({ href, key, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2.5 py-2 text-[13px] text-muted transition-colors hover:bg-celadon-wash hover:text-ink md:w-[64px] md:flex-col md:gap-1 md:px-1 md:text-[11px]",
                  active && "bg-celadon-wash text-celadon-deep",
                )}
              >
                <Icon className="size-[18px]" />
                <span>{t(key)}</span>
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center gap-1 md:flex-col">
          <Tooltip content={t("nav.api")} side="right">
            <a
              href={`${API_URL}/docs`}
              target="_blank"
              rel="noreferrer"
              className="rounded-md p-2 text-muted hover:bg-celadon-wash hover:text-ink"
              aria-label={t("nav.api")}
            >
              <BookOpenText className="size-[18px]" />
            </a>
          </Tooltip>
          <Tooltip content={t("lang.toggle")} side="right">
            <button
              type="button"
              onClick={() => setLocale(locale === "ko" ? "en" : "ko")}
              className="flex items-center gap-1 rounded-md p-2 text-muted hover:bg-celadon-wash hover:text-ink"
              aria-label={t("lang.toggle")}
            >
              <Languages className="size-[18px]" />
              <span className="text-[11px] font-semibold">{locale === "ko" ? "EN" : "한"}</span>
            </button>
          </Tooltip>
          <Tooltip content={t("theme.toggle")} side="right">
            <button
              type="button"
              onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
              className="rounded-md p-2 text-muted hover:bg-celadon-wash hover:text-ink"
              aria-label={t("theme.toggle")}
            >
              <Sun className="hidden size-[18px] dark:block" />
              <Moon className="size-[18px] dark:hidden" />
            </button>
          </Tooltip>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <ApiStatus />
        {children}
      </div>
    </div>
  );
}
