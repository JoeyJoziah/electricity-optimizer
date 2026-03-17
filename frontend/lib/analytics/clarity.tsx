'use client'

import Script from 'next/script'
import { CLARITY_PROJECT_ID } from '@/lib/config/env'

export function ClarityScript({ nonce }: { nonce?: string }) {
  if (!CLARITY_PROJECT_ID) return null

  return (
    <Script
      id="microsoft-clarity"
      strategy="afterInteractive"
      nonce={nonce}
      dangerouslySetInnerHTML={{
        __html: `
          (function(c,l,a,r,i,t,y){
            c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
            t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
            y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
          })(window,document,"clarity","script","${CLARITY_PROJECT_ID}");
        `,
      }}
    />
  )
}
