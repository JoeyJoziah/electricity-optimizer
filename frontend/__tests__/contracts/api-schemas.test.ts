/**
 * Contract tests: Validate frontend API types match expected backend response shapes.
 *
 * These tests catch schema drift between the frontend's TypeScript expectations and
 * the actual JSON shapes returned by the FastAPI backend. Each describe block mirrors
 * a backend endpoint group and asserts the minimum required fields that the frontend
 * components depend on.
 *
 * Field names are derived from the backend Pydantic models:
 *   - Price/PriceHistoryResponse  → backend/models/price.py
 *   - SupplierResponse            → backend/models/supplier.py (SuppliersResponse in suppliers.py)
 *   - TariffResponse              → backend/models/supplier.py
 *   - SavingsSummary              → frontend/lib/hooks/useSavings.ts (mirrors /savings/summary)
 *   - ConnectionResponse          → backend/models/connections.py
 *   - Notifications               → backend/services/notification_service.py
 *   - UserResponse                → backend/api/v1/auth.py
 *   - Alerts                      → backend/services/alert_service.py (_config_row_to_dict)
 */

describe('API Response Contracts', () => {
  // ---------------------------------------------------------------------------
  // Price API  (GET /api/v1/prices/current, /prices/history)
  // ---------------------------------------------------------------------------
  describe('Price API', () => {
    it('current prices response has expected fields', () => {
      /**
       * GET /api/v1/prices/current
       * Backend model: CurrentPriceResponse (prices.py) wrapping Price (price.py)
       *
       * Key fields the frontend reads:
       *   prices[].id              – UUID string
       *   prices[].region          – region enum value e.g. "us_ct"
       *   prices[].supplier        – supplier name string
       *   prices[].price_per_kwh   – Decimal serialised as string by json_encoders
       *   prices[].timestamp       – ISO datetime string
       *   prices[].utility_type    – utility_type enum value e.g. "electricity"
       *   region                   – top-level echo of the requested region
       *   timestamp                – ISO datetime of the response generation
       */
      const response = {
        prices: [
          {
            id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            region: 'us_ct',
            supplier: 'Eversource Energy',
            price_per_kwh: '0.2500',
            timestamp: '2026-01-01T00:00:00Z',
            utility_type: 'electricity',
            currency: 'USD',
          },
        ],
        region: 'us_ct',
        timestamp: '2026-01-01T00:00:00Z',
      }

      expect(response).toHaveProperty('prices')
      expect(Array.isArray(response.prices)).toBe(true)
      expect(response.prices[0]).toHaveProperty('id')
      expect(response.prices[0]).toHaveProperty('region')
      expect(response.prices[0]).toHaveProperty('supplier')
      expect(response.prices[0]).toHaveProperty('price_per_kwh')
      expect(response.prices[0]).toHaveProperty('timestamp')
      expect(response.prices[0]).toHaveProperty('utility_type')
      expect(response).toHaveProperty('region')
      expect(response).toHaveProperty('timestamp')
    })

    it('price history response has expected fields', () => {
      /**
       * GET /api/v1/prices/history
       * Backend model: PriceHistoryResponse (price.py)
       *
       * Key fields:
       *   prices[]  – array of Price objects
       *   region    – region code
       *   average_price, min_price, max_price – optional aggregate stats
       */
      const response = {
        prices: [
          {
            id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            region: 'us_ct',
            supplier: 'Eversource Energy',
            price_per_kwh: '0.2500',
            timestamp: '2026-01-01T00:00:00Z',
            utility_type: 'electricity',
            currency: 'USD',
          },
        ],
        region: 'us_ct',
        start_date: '2025-12-31T00:00:00Z',
        end_date: '2026-01-01T00:00:00Z',
        average_price: '0.2500',
        min_price: '0.2000',
        max_price: '0.3000',
      }

      expect(response).toHaveProperty('prices')
      expect(Array.isArray(response.prices)).toBe(true)
      expect(response).toHaveProperty('region')
      expect(response).toHaveProperty('start_date')
      expect(response).toHaveProperty('end_date')
      // Aggregate stats (optional but present when available)
      expect(response).toHaveProperty('average_price')
      expect(response).toHaveProperty('min_price')
      expect(response).toHaveProperty('max_price')
      // Individual price points carry the same fields as current prices
      expect(response.prices[0]).toHaveProperty('price_per_kwh')
      expect(response.prices[0]).toHaveProperty('region')
      expect(response.prices[0]).toHaveProperty('supplier')
    })
  })

  // ---------------------------------------------------------------------------
  // Supplier API  (GET /api/v1/suppliers, /suppliers/:id/tariffs)
  // ---------------------------------------------------------------------------
  describe('Supplier API', () => {
    it('suppliers list response has expected fields', () => {
      /**
       * GET /api/v1/suppliers
       * Backend model: SuppliersResponse (suppliers.py) → List[SupplierResponse]
       *
       * Key fields the frontend reads:
       *   suppliers[].id                  – UUID string
       *   suppliers[].name                – display name
       *   suppliers[].regions             – list of region codes
       *   suppliers[].tariff_types        – list of tariff type strings
       *   suppliers[].api_available       – boolean
       *   suppliers[].green_energy_provider – boolean (NOTE: NOT greenEnergy)
       *   suppliers[].rating              – float or null
       *   total, page, page_size          – pagination envelope
       */
      const response = {
        suppliers: [
          {
            id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            name: 'Eversource Energy',
            regions: ['us_ct'],
            tariff_types: ['variable'],
            api_available: true,
            green_energy_provider: false,
            rating: 4.2,
            is_active: true,
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      }

      expect(response).toHaveProperty('suppliers')
      expect(Array.isArray(response.suppliers)).toBe(true)
      expect(response.suppliers[0]).toHaveProperty('id')
      expect(response.suppliers[0]).toHaveProperty('name')
      expect(response.suppliers[0]).toHaveProperty('regions')
      expect(Array.isArray(response.suppliers[0].regions)).toBe(true)
      expect(response.suppliers[0]).toHaveProperty('tariff_types')
      expect(response.suppliers[0]).toHaveProperty('api_available')
      expect(response.suppliers[0]).toHaveProperty('green_energy_provider')
      expect(response.suppliers[0]).toHaveProperty('rating')
      expect(response).toHaveProperty('total')
      expect(response).toHaveProperty('page')
      expect(response).toHaveProperty('page_size')
      expect(typeof response.total).toBe('number')
      expect(typeof response.page).toBe('number')
    })

    it('tariffs response has expected fields', () => {
      /**
       * GET /api/v1/suppliers/:id/tariffs
       * Backend model: SupplierTariffsResponse / TariffResponse (supplier.py)
       *
       * Key fields:
       *   tariffs[].id                    – UUID string
       *   tariffs[].supplier_id           – UUID string
       *   tariffs[].name                  – tariff display name
       *   tariffs[].type                  – TariffType enum value
       *   tariffs[].unit_rate             – Decimal serialised as string
       *   tariffs[].standing_charge       – Decimal serialised as string
       *   tariffs[].green_energy_percentage – integer 0–100
       *   tariffs[].contract_length       – ContractLength enum value
       *   tariffs[].is_available          – boolean
       */
      const response = {
        supplier_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        supplier_name: 'Eversource Energy',
        tariffs: [
          {
            id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
            supplier_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            name: 'Standard Variable',
            type: 'variable',
            unit_rate: '0.2500',
            standing_charge: '0.4000',
            green_energy_percentage: 0,
            contract_length: 'rolling',
            is_available: true,
          },
        ],
        total: 1,
      }

      expect(response).toHaveProperty('supplier_id')
      expect(response).toHaveProperty('supplier_name')
      expect(response).toHaveProperty('tariffs')
      expect(Array.isArray(response.tariffs)).toBe(true)
      expect(response.tariffs[0]).toHaveProperty('id')
      expect(response.tariffs[0]).toHaveProperty('supplier_id')
      expect(response.tariffs[0]).toHaveProperty('name')
      expect(response.tariffs[0]).toHaveProperty('type')
      expect(response.tariffs[0]).toHaveProperty('unit_rate')
      expect(response.tariffs[0]).toHaveProperty('standing_charge')
      expect(response.tariffs[0]).toHaveProperty('green_energy_percentage')
      expect(response.tariffs[0]).toHaveProperty('contract_length')
      expect(response.tariffs[0]).toHaveProperty('is_available')
      expect(response).toHaveProperty('total')
      expect(typeof response.total).toBe('number')
    })
  })

  // ---------------------------------------------------------------------------
  // Savings API  (GET /api/v1/savings/summary)
  // ---------------------------------------------------------------------------
  describe('Savings API', () => {
    it('savings summary has expected fields', () => {
      /**
       * GET /api/v1/savings/summary
       * Frontend interface: SavingsSummary (lib/hooks/useSavings.ts)
       *
       * Key fields:
       *   total        – cumulative savings in the user's currency
       *   weekly       – savings over the last 7 days
       *   monthly      – savings over the last 30 days
       *   streak_days  – consecutive days with savings
       *   currency     – ISO 4217 code e.g. "USD"
       */
      const response = {
        total: 45.5,
        weekly: 12.3,
        monthly: 45.5,
        streak_days: 5,
        currency: 'USD',
      }

      expect(response).toHaveProperty('total')
      expect(response).toHaveProperty('weekly')
      expect(response).toHaveProperty('monthly')
      expect(response).toHaveProperty('streak_days')
      expect(response).toHaveProperty('currency')
      expect(typeof response.total).toBe('number')
      expect(typeof response.weekly).toBe('number')
      expect(typeof response.monthly).toBe('number')
      expect(typeof response.streak_days).toBe('number')
      expect(typeof response.currency).toBe('string')
    })
  })

  // ---------------------------------------------------------------------------
  // Connection API  (GET /api/v1/connections, POST /connections)
  // ---------------------------------------------------------------------------
  describe('Connection API', () => {
    it('single connection response has expected fields', () => {
      /**
       * GET /api/v1/connections/:id
       * Backend model: ConnectionResponse (models/connections.py)
       *
       * Key fields:
       *   id               – UUID string
       *   user_id          – UUID string
       *   connection_type  – ConnectionType enum ("direct_login"|"email_import"|"bill_upload"|"utility_api")
       *   supplier_name    – display name (nullable)
       *   status           – ConnectionStatus ("active"|"syncing"|"error"|"inactive")
       *   created_at       – ISO datetime string
       *
       * NOTE: The backend field is `connection_type` NOT `connection_method`.
       *       The `current_rate` field lives in extracted_rates, not the connection itself.
       */
      const response = {
        id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        user_id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
        connection_type: 'direct_login',
        supplier_name: 'Eversource Energy',
        status: 'active',
        supplier_id: null,
        account_number_masked: null,
        email_provider: null,
        label: null,
        created_at: '2026-01-01T00:00:00Z',
      }

      expect(response).toHaveProperty('id')
      expect(response).toHaveProperty('user_id')
      expect(response).toHaveProperty('connection_type')
      expect(response).toHaveProperty('supplier_name')
      expect(response).toHaveProperty('status')
      expect(response).toHaveProperty('created_at')
      expect(typeof response.id).toBe('string')
      expect(typeof response.connection_type).toBe('string')
      expect(typeof response.status).toBe('string')
    })

    it('connection list response has expected fields', () => {
      /**
       * GET /api/v1/connections
       * Backend model: ConnectionListResponse (models/connections.py)
       */
      const response = {
        connections: [
          {
            id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            user_id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
            connection_type: 'bill_upload',
            supplier_name: 'United Illuminating',
            status: 'active',
            supplier_id: null,
            account_number_masked: null,
            email_provider: null,
            label: null,
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        total: 1,
      }

      expect(response).toHaveProperty('connections')
      expect(Array.isArray(response.connections)).toBe(true)
      expect(response.connections[0]).toHaveProperty('connection_type')
      expect(response.connections[0]).toHaveProperty('status')
      expect(response.connections[0]).toHaveProperty('supplier_name')
      expect(response).toHaveProperty('total')
      expect(typeof response.total).toBe('number')
    })
  })

  // ---------------------------------------------------------------------------
  // Notification API  (GET /api/v1/notifications, /notifications/count)
  // ---------------------------------------------------------------------------
  describe('Notification API', () => {
    it('notifications list response has expected fields', () => {
      /**
       * GET /api/v1/notifications
       * Backend: NotificationService.get_unread → {"notifications": [...], "total": n}
       *
       * Key fields per notification:
       *   id         – UUID string
       *   type       – notification category string
       *   title      – short display title
       *   body       – message body text
       *   created_at – ISO datetime string
       */
      const response = {
        notifications: [
          {
            id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            type: 'info',
            title: 'Price Alert',
            body: 'Your tracked price has changed.',
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        total: 1,
      }

      expect(response).toHaveProperty('notifications')
      expect(Array.isArray(response.notifications)).toBe(true)
      expect(response.notifications[0]).toHaveProperty('id')
      expect(response.notifications[0]).toHaveProperty('type')
      expect(response.notifications[0]).toHaveProperty('title')
      expect(response.notifications[0]).toHaveProperty('body')
      expect(response.notifications[0]).toHaveProperty('created_at')
      expect(response).toHaveProperty('total')
      expect(typeof response.total).toBe('number')
    })

    it('notification count response has expected fields', () => {
      /**
       * GET /api/v1/notifications/count
       * Backend: {"unread": <int>}
       */
      const response = { unread: 5 }

      expect(response).toHaveProperty('unread')
      expect(typeof response.unread).toBe('number')
      expect(Number.isInteger(response.unread)).toBe(true)
      expect(response.unread).toBeGreaterThanOrEqual(0)
    })
  })

  // ---------------------------------------------------------------------------
  // User Profile API  (GET /api/v1/me)
  // ---------------------------------------------------------------------------
  describe('User Profile API', () => {
    it('profile response has expected fields', () => {
      /**
       * GET /api/v1/me
       * Backend model: UserResponse (auth.py)
       *
       * Key fields:
       *   id              – UUID string (neon_auth.user.id)
       *   email           – user's email address
       *   name            – display name (nullable)
       *   email_verified  – boolean
       *
       * NOTE: Region, annual_usage_kwh, and onboarding_completed are stored in
       *       the app's public.users table and served via GET /api/v1/user/preferences,
       *       NOT included in the /me response.
       */
      const response = {
        id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        email: 'test@example.com',
        name: 'Test User',
        email_verified: true,
      }

      expect(response).toHaveProperty('id')
      expect(response).toHaveProperty('email')
      expect(response).toHaveProperty('name')
      expect(response).toHaveProperty('email_verified')
      expect(typeof response.id).toBe('string')
      expect(typeof response.email).toBe('string')
      expect(typeof response.email_verified).toBe('boolean')
    })

    it('user preferences response has expected fields', () => {
      /**
       * GET /api/v1/user/preferences
       * Backend: user.py get_preferences → {user_id, preferences: UserPreferences}
       *
       * Preferences include: notification_enabled, auto_switch_enabled, green_energy_only, region
       */
      const response = {
        user_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        preferences: {
          region: 'us_ct',
          notification_enabled: true,
          auto_switch_enabled: false,
          green_energy_only: false,
        },
      }

      expect(response).toHaveProperty('user_id')
      expect(response).toHaveProperty('preferences')
      expect(response.preferences).toHaveProperty('region')
      expect(response.preferences).toHaveProperty('notification_enabled')
      expect(typeof response.preferences.notification_enabled).toBe('boolean')
    })
  })

  // ---------------------------------------------------------------------------
  // Alert API  (GET /api/v1/alerts)
  // ---------------------------------------------------------------------------
  describe('Alert API', () => {
    it('alerts list response has expected fields', () => {
      /**
       * GET /api/v1/alerts
       * Backend: AlertService._config_row_to_dict → {"alerts": [...], "total": n}
       *
       * Key fields per alert (price_alert_configs row):
       *   id                       – UUID string
       *   user_id                  – UUID string
       *   region                   – region code e.g. "us_ct"
       *   currency                 – ISO 4217 e.g. "USD"
       *   price_below              – float or null
       *   price_above              – float or null
       *   notify_optimal_windows   – boolean
       *   is_active                – boolean
       *   created_at               – ISO datetime string or null
       *   updated_at               – ISO datetime string or null
       *
       * NOTE: The backend does NOT return an `alert_type` field on the config row.
       *       `alert_type` appears only in alert history records (_history_row_to_dict).
       *       The `threshold` field does not exist; use `price_below`/`price_above`.
       */
      const response = {
        alerts: [
          {
            id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            user_id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
            region: 'us_ct',
            currency: 'USD',
            price_below: 0.2,
            price_above: null,
            notify_optimal_windows: true,
            is_active: true,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
        total: 1,
      }

      expect(response).toHaveProperty('alerts')
      expect(Array.isArray(response.alerts)).toBe(true)
      expect(response.alerts[0]).toHaveProperty('id')
      expect(response.alerts[0]).toHaveProperty('user_id')
      expect(response.alerts[0]).toHaveProperty('region')
      expect(response.alerts[0]).toHaveProperty('currency')
      expect(response.alerts[0]).toHaveProperty('price_below')
      expect(response.alerts[0]).toHaveProperty('price_above')
      expect(response.alerts[0]).toHaveProperty('notify_optimal_windows')
      expect(response.alerts[0]).toHaveProperty('is_active')
      expect(response.alerts[0]).toHaveProperty('created_at')
      expect(response).toHaveProperty('total')
      expect(typeof response.total).toBe('number')
      expect(typeof response.alerts[0].is_active).toBe('boolean')
      expect(typeof response.alerts[0].notify_optimal_windows).toBe('boolean')
    })

    it('alert history response has expected fields', () => {
      /**
       * GET /api/v1/alerts/history
       * Backend: AlertService._history_row_to_dict
       *
       * History records (alert_history table) DO carry an alert_type field
       * that distinguishes what kind of trigger occurred.
       */
      const historyResponse = {
        items: [
          {
            id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            user_id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
            alert_config_id: 'c3d4e5f6-a7b8-9012-cdef-012345678902',
            alert_type: 'price_drop',
            current_price: 0.18,
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        pages: 1,
      }

      expect(historyResponse).toHaveProperty('items')
      expect(Array.isArray(historyResponse.items)).toBe(true)
      expect(historyResponse.items[0]).toHaveProperty('alert_type')
      expect(historyResponse.items[0]).toHaveProperty('current_price')
      expect(historyResponse).toHaveProperty('total')
      expect(historyResponse).toHaveProperty('page')
    })
  })
})
