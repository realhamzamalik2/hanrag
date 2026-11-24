import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "HanRAG, Korean and English document Q&A",
  description:
    "Ask questions about Korean and English documents. Hybrid search with Kiwi BM25, bge-m3 vectors and a reranker, with every claim cited to its page.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
