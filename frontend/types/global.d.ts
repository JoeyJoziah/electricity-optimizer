/** Google Analytics gtag.js global */
interface GtagEventParams {
  event_category?: string
  event_label?: string
  value?: number
  [key: string]: string | number | undefined
}

interface Window {
  gtag?: (command: 'event', action: string, params?: GtagEventParams) => void
}
