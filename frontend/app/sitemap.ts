import { MetadataRoute } from "next";
import { US_STATES, UTILITY_TYPES, stateToSlug } from "@/lib/config/seo";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://rateshift.app";

  const staticPages: MetadataRoute.Sitemap = [
    {
      url: baseUrl,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${baseUrl}/pricing`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 0.8,
    },
    {
      url: `${baseUrl}/privacy`,
      lastModified: new Date(),
      changeFrequency: "yearly",
      priority: 0.3,
    },
    {
      url: `${baseUrl}/terms`,
      lastModified: new Date(),
      changeFrequency: "yearly",
      priority: 0.3,
    },
  ];

  // Programmatic rate pages: /rates/[state]/[utility]
  const ratePages: MetadataRoute.Sitemap = [];
  const changeFrequencyMap: Record<string, "daily" | "weekly"> = {
    electricity: "daily",
    natural_gas: "weekly",
    heating_oil: "weekly",
  };

  for (const [, stateName] of Object.entries(US_STATES)) {
    for (const [key, val] of Object.entries(UTILITY_TYPES)) {
      ratePages.push({
        url: `${baseUrl}/rates/${stateToSlug(stateName)}/${val.slug}`,
        lastModified: new Date(),
        changeFrequency: changeFrequencyMap[key] ?? "weekly",
        priority: 0.6,
      });
    }
  }

  return [...staticPages, ...ratePages];
}
