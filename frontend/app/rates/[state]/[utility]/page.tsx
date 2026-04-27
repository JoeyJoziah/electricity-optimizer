import { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  US_STATES,
  UTILITY_TYPES,
  slugToStateCode,
  slugToUtilityKey,
  stateToSlug,
  BASE_URL,
} from "@/lib/config/seo";
import { RatePageContent } from "@/components/seo/RatePageContent";

interface PageProps {
  params: Promise<{ state: string; utility: string }>;
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { state: stateSlug, utility: utilitySlug } = await params;
  const stateCode = slugToStateCode(stateSlug);
  const utilityKey = slugToUtilityKey(utilitySlug);

  if (!stateCode || !utilityKey) return {};

  const stateName = US_STATES[stateCode];
  const utilityType = UTILITY_TYPES[utilityKey];
  if (!stateName || !utilityType) return {};
  const utilityLabel = utilityType.label;

  const title = `${utilityLabel} Rates in ${stateName} — RateShift`;
  const description = `Compare current ${utilityLabel.toLowerCase()} rates in ${stateName}. See average prices, top suppliers, and find the best deal.`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      url: `${BASE_URL}/rates/${stateSlug}/${utilitySlug}`,
      type: "website",
    },
    alternates: {
      canonical: `${BASE_URL}/rates/${stateSlug}/${utilitySlug}`,
    },
  };
}

export async function generateStaticParams() {
  const params: { state: string; utility: string }[] = [];
  for (const [code, name] of Object.entries(US_STATES)) {
    for (const [, val] of Object.entries(UTILITY_TYPES)) {
      params.push({ state: stateToSlug(name), utility: val.slug });
    }
  }
  return params;
}

export const revalidate = 3600; // ISR: revalidate every hour

export default async function RatePage({ params }: PageProps) {
  const { state: stateSlug, utility: utilitySlug } = await params;
  const stateCode = slugToStateCode(stateSlug);
  const utilityKey = slugToUtilityKey(utilitySlug);

  if (!stateCode || !utilityKey) notFound();

  const stateName = US_STATES[stateCode];
  const utilityInfo = UTILITY_TYPES[utilityKey];
  if (!stateName || !utilityInfo) notFound();

  // Fetch data server-side for SEO
  let rateData = null;
  try {
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
    const res = await fetch(
      `${backendUrl}/api/v1/public/rates/${stateCode}/${utilityKey}`,
      { next: { revalidate: 3600 }, signal: AbortSignal.timeout(10_000) },
    );
    if (res.ok) {
      rateData = await res.json();
    }
  } catch {
    // Render with null data — component handles empty state
  }

  const breadcrumbs = [
    { name: "Home", url: BASE_URL },
    { name: "Rates", url: `${BASE_URL}/rates` },
    { name: stateName, url: `${BASE_URL}/rates/${stateSlug}` },
    {
      name: utilityInfo.label,
      url: `${BASE_URL}/rates/${stateSlug}/${utilitySlug}`,
    },
  ];

  // JSON-LD structured data
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: `${utilityInfo.label} Rates in ${stateName}`,
    description: `Current ${utilityInfo.label.toLowerCase()} rates and suppliers in ${stateName}.`,
    url: `${BASE_URL}/rates/${stateSlug}/${utilitySlug}`,
    breadcrumb: {
      "@type": "BreadcrumbList",
      itemListElement: breadcrumbs.map((b, i) => ({
        "@type": "ListItem",
        position: i + 1,
        name: b.name,
        item: b.url,
      })),
    },
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <RatePageContent
        stateCode={stateCode}
        stateName={stateName}
        utilityKey={utilityKey}
        utilityLabel={utilityInfo.label}
        unit={utilityInfo.unit}
        rateData={rateData}
        breadcrumbs={breadcrumbs}
      />
    </>
  );
}
