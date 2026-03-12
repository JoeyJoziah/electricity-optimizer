import { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  const baseUrl =
    process.env.NEXT_PUBLIC_SITE_URL || 'https://rateshift.app'

  return {
    rules: {
      userAgent: '*',
      allow: ['/', '/rates/'],
      disallow: ['/api/', '/dashboard/', '/settings/', '/onboarding/'],
    },
    sitemap: `${baseUrl}/sitemap.xml`,
  }
}
