import { Suspense } from "react";

import { DocumentView } from "./document-view";

export default async function DocumentPage({ params }: PageProps<"/documents/[id]">) {
  const { id } = await params;
  return (
    <Suspense>
      <DocumentView id={id} />
    </Suspense>
  );
}
