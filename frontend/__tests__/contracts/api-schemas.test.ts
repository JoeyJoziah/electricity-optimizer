/**
 * Contract tests: Validate frontend API types match expected backend response shapes.
 *
 * Each test mocks global.fetch with a realistic backend JSON payload, calls the
 * real API client function (from lib/api/*), and asserts on the returned object.
 * This proves the API client parses responses into the correct shape — not that a
 * hand-written literal contains the properties you just gave it.
 *
 * Field names are derived from the backend Pydantic models:
 *   - Price/PriceHistoryResponse  → backend/models/price.py
 *   - SupplierResponse            → backend/models/supplier.py (SuppliersResponse in suppliers.py)
 *   - TariffResponse              → backend/models/supplier.py
 *   - SavingsSummary              → frontend/lib/hooks/useSavings.ts (mirrors /savings/summary)
 *   - ConnectionResponse          → backend/models/connections.py
 *   - Notifications               → backend/services/notification_service.py
 *   - UserProfile                 → backend/api/v1/users.py  (GET /users/profile)
 *   - Alerts                      → backend/services/alert_service.py (_config_row_to_dict)
 */

import { getCurrentPrices, getPriceHistory } from "@/lib/api/prices";
import { getSuppliers } from "@/lib/api/suppliers";
import {
  getNotifications,
  getNotificationCount,
} from "@/lib/api/notifications";
import { getAlerts, getAlertHistory } from "@/lib/api/alerts";
import { getUserProfile } from "@/lib/api/profile";
import { apiClient, _resetRedirectState } from "@/lib/api/client";
import type {
  GetAlertsResponse,
  GetAlertHistoryResponse,
} from "@/lib/api/alerts";
import type {
  GetNotificationsResponse,
  GetNotificationCountResponse,
} from "@/lib/api/notifications";

// ---------------------------------------------------------------------------
// Shared test helpers
// ---------------------------------------------------------------------------

const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>;

function mockJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: jest.fn().mockResolvedValue(body),
    headers: new Headers(),
    redirected: false,
    type: "basic",
    url: "",
    clone: jest.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: jest.fn(),
    blob: jest.fn(),
    formData: jest.fn(),
    text: jest.fn(),
    bytes: jest.fn(),
  } as unknown as Response;
}

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
});

// ---------------------------------------------------------------------------
// Price API  (GET /api/v1/prices/current, /prices/history)
// ---------------------------------------------------------------------------

describe("API Response Contracts", () => {
  describe("Price API", () => {
    it("current prices response has expected fields", async () => {
      /**
       * GET /api/v1/prices/current
       * Backend model: CurrentPriceResponse (prices.py) wrapping ApiPriceResponse
       *
       * Key fields the frontend reads:
       *   prices[].ticker         – "ELEC-US_CT" format
       *   prices[].region         – region enum value e.g. "us_ct"
       *   prices[].supplier       – supplier name string
       *   prices[].current_price  – Decimal serialised as string (ApiPriceResponse)
       *   prices[].updated_at     – ISO datetime string
       *   region                  – top-level echo of the requested region
       *   timestamp               – ISO datetime of the response generation
       */
      const backendPayload = {
        prices: [
          {
            ticker: "ELEC-US_CT",
            current_price: "0.2500",
            currency: "USD",
            region: "us_ct",
            supplier: "Eversource Energy",
            updated_at: "2026-01-01T00:00:00Z",
            is_peak: null,
            carbon_intensity: null,
            price_change_24h: null,
          },
        ],
        price: null,
        region: "us_ct",
        timestamp: "2026-01-01T00:00:00Z",
        source: null,
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await getCurrentPrices({ region: "us_ct" });

      expect(result).toHaveProperty("prices");
      expect(Array.isArray(result.prices)).toBe(true);
      const price = result.prices![0]!;
      expect(price).toHaveProperty("ticker");
      expect(price).toHaveProperty("region");
      expect(price).toHaveProperty("supplier");
      expect(price).toHaveProperty("current_price");
      expect(price).toHaveProperty("updated_at");
      expect(typeof price.current_price).toBe("string");
      expect(typeof price.supplier).toBe("string");
      expect(result).toHaveProperty("region");
      expect(result).toHaveProperty("timestamp");
    });

    it("price history response has expected fields", async () => {
      /**
       * GET /api/v1/prices/history
       * Backend model: PriceHistoryResponse (price.py)
       *
       * Key fields:
       *   prices[]      – array of full ApiPrice objects (with price_per_kwh)
       *   region        – region code
       *   start_date, end_date  – ISO datetime bounds
       *   average_price, min_price, max_price – optional aggregate stats (Decimal strings)
       */
      const backendPayload = {
        region: "us_ct",
        supplier: null,
        start_date: "2025-12-31T00:00:00Z",
        end_date: "2026-01-01T00:00:00Z",
        prices: [
          {
            id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            region: "us_ct",
            supplier: "Eversource Energy",
            price_per_kwh: "0.2500",
            timestamp: "2026-01-01T00:00:00Z",
            currency: "USD",
            utility_type: "electricity",
            unit: "kWh",
            is_peak: null,
            carbon_intensity: null,
            energy_source: null,
            tariff_name: null,
            energy_cost: null,
            network_cost: null,
            taxes: null,
            levies: null,
            source_api: null,
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
        average_price: "0.2500",
        min_price: "0.2000",
        max_price: "0.3000",
        source: null,
        total: 1,
        page: 1,
        page_size: 24,
        pages: 1,
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await getPriceHistory({ region: "us_ct", days: 1 });

      expect(result).toHaveProperty("prices");
      expect(Array.isArray(result.prices)).toBe(true);
      expect(result).toHaveProperty("region");
      expect(result).toHaveProperty("start_date");
      expect(result).toHaveProperty("end_date");
      // Aggregate stats
      expect(result).toHaveProperty("average_price");
      expect(result).toHaveProperty("min_price");
      expect(result).toHaveProperty("max_price");
      // Individual price points carry price_per_kwh (Decimal string)
      const point = result.prices[0]!;
      expect(point).toHaveProperty("price_per_kwh");
      expect(point).toHaveProperty("region");
      expect(point).toHaveProperty("supplier");
      expect(typeof point.price_per_kwh).toBe("string");
    });
  });

  // ---------------------------------------------------------------------------
  // Supplier API  (GET /api/v1/suppliers, /suppliers/:id/tariffs)
  // ---------------------------------------------------------------------------
  describe("Supplier API", () => {
    it("suppliers list response has expected fields", async () => {
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
       *   suppliers[].green_energy_provider – boolean (NOT greenEnergy)
       *   suppliers[].rating              – float or null
       *   total, page, page_size          – pagination envelope
       */
      const backendPayload = {
        suppliers: [
          {
            id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            name: "Eversource Energy",
            regions: ["us_ct"],
            tariff_types: ["variable"],
            api_available: true,
            green_energy_provider: false,
            rating: 4.2,
            is_active: true,
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await getSuppliers("us_ct");

      expect(result).toHaveProperty("suppliers");
      expect(Array.isArray(result.suppliers)).toBe(true);
      const supplier = result.suppliers[0]!;
      expect(supplier).toHaveProperty("id");
      expect(supplier).toHaveProperty("name");
      expect(supplier).toHaveProperty("regions");
      expect(Array.isArray(supplier.regions)).toBe(true);
      expect(supplier).toHaveProperty("tariff_types");
      expect(supplier).toHaveProperty("api_available");
      expect(supplier).toHaveProperty("green_energy_provider");
      expect(supplier).toHaveProperty("rating");
      expect(typeof supplier.id).toBe("string");
      expect(typeof supplier.name).toBe("string");
      // Pagination envelope
      expect(result).toHaveProperty("total");
      expect(typeof result.total).toBe("number");
    });

    it("tariffs response has expected fields", async () => {
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
      const backendPayload = {
        supplier_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        supplier_name: "Eversource Energy",
        tariffs: [
          {
            id: "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            supplier_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            name: "Standard Variable",
            type: "variable",
            unit_rate: "0.2500",
            standing_charge: "0.4000",
            green_energy_percentage: 0,
            contract_length: "rolling",
            is_available: true,
          },
        ],
        total: 1,
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      // No standalone export — use apiClient directly (same as component usage)
      const result = await apiClient.get<typeof backendPayload>(
        "/suppliers/a1b2c3d4-e5f6-7890-abcd-ef1234567890/tariffs",
      );

      expect(result).toHaveProperty("supplier_id");
      expect(result).toHaveProperty("supplier_name");
      expect(result).toHaveProperty("tariffs");
      expect(Array.isArray(result.tariffs)).toBe(true);
      const tariff = result.tariffs[0]!;
      expect(tariff).toHaveProperty("id");
      expect(tariff).toHaveProperty("supplier_id");
      expect(tariff).toHaveProperty("name");
      expect(tariff).toHaveProperty("type");
      expect(tariff).toHaveProperty("unit_rate");
      expect(tariff).toHaveProperty("standing_charge");
      expect(tariff).toHaveProperty("green_energy_percentage");
      expect(tariff).toHaveProperty("contract_length");
      expect(tariff).toHaveProperty("is_available");
      expect(typeof tariff.unit_rate).toBe("string");
      expect(typeof tariff.standing_charge).toBe("string");
      expect(result).toHaveProperty("total");
      expect(typeof result.total).toBe("number");
    });
  });

  // ---------------------------------------------------------------------------
  // Savings API  (GET /api/v1/savings/summary)
  // ---------------------------------------------------------------------------
  describe("Savings API", () => {
    it("savings summary has expected fields", async () => {
      /**
       * GET /api/v1/savings/summary
       * Frontend interface: SavingsSummary (lib/hooks/useSavings.ts)
       *
       * Key fields:
       *   total        – cumulative savings in the user's currency (number)
       *   weekly       – savings over the last 7 days
       *   monthly      – savings over the last 30 days
       *   streak_days  – consecutive days with savings (integer)
       *   currency     – ISO 4217 code e.g. "USD"
       */
      const backendPayload = {
        total: 45.5,
        weekly: 12.3,
        monthly: 45.5,
        streak_days: 5,
        currency: "USD",
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      // apiClient.get is used directly by useSavingsSummary hook
      const result =
        await apiClient.get<typeof backendPayload>("/savings/summary");

      expect(result).toHaveProperty("total");
      expect(result).toHaveProperty("weekly");
      expect(result).toHaveProperty("monthly");
      expect(result).toHaveProperty("streak_days");
      expect(result).toHaveProperty("currency");
      expect(typeof result.total).toBe("number");
      expect(typeof result.weekly).toBe("number");
      expect(typeof result.monthly).toBe("number");
      expect(typeof result.streak_days).toBe("number");
      expect(typeof result.currency).toBe("string");
    });
  });

  // ---------------------------------------------------------------------------
  // Connection API  (GET /api/v1/connections)
  // ---------------------------------------------------------------------------
  describe("Connection API", () => {
    it("single connection response has expected fields", async () => {
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
       */
      const backendPayload = {
        id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        user_id: "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        connection_type: "direct_login",
        supplier_name: "Eversource Energy",
        status: "active",
        supplier_id: null,
        account_number_masked: null,
        email_provider: null,
        label: null,
        created_at: "2026-01-01T00:00:00Z",
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await apiClient.get<typeof backendPayload>(
        "/connections/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      );

      expect(result).toHaveProperty("id");
      expect(result).toHaveProperty("user_id");
      expect(result).toHaveProperty("connection_type");
      expect(result).toHaveProperty("supplier_name");
      expect(result).toHaveProperty("status");
      expect(result).toHaveProperty("created_at");
      expect(typeof result.id).toBe("string");
      expect(typeof result.connection_type).toBe("string");
      expect(typeof result.status).toBe("string");
    });

    it("connection list response has expected fields", async () => {
      /**
       * GET /api/v1/connections
       * Backend model: ConnectionListResponse (models/connections.py)
       * Frontend: useConnections hook (lib/hooks/useConnections.ts) maps
       *           connection_type → method for display compatibility.
       */
      const backendPayload = {
        connections: [
          {
            id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            user_id: "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            connection_type: "bill_upload",
            supplier_name: "United Illuminating",
            status: "active",
            supplier_id: null,
            account_number_masked: null,
            email_provider: null,
            label: null,
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await apiClient.get<typeof backendPayload>("/connections");

      expect(result).toHaveProperty("connections");
      expect(Array.isArray(result.connections)).toBe(true);
      const conn = result.connections[0]!;
      expect(conn).toHaveProperty("connection_type");
      expect(conn).toHaveProperty("status");
      expect(conn).toHaveProperty("supplier_name");
      expect(conn).toHaveProperty("created_at");
      expect(typeof conn.connection_type).toBe("string");
      expect(typeof conn.status).toBe("string");
      expect(result).toHaveProperty("total");
      expect(typeof result.total).toBe("number");
    });
  });

  // ---------------------------------------------------------------------------
  // Notification API  (GET /api/v1/notifications, /notifications/count)
  // ---------------------------------------------------------------------------
  describe("Notification API", () => {
    it("notifications list response has expected fields", async () => {
      /**
       * GET /api/v1/notifications
       * Backend: NotificationService.get_unread → {"notifications": [...], "total": n}
       *
       * Key fields per notification:
       *   id         – UUID string
       *   type       – notification category string
       *   title      – short display title
       *   body       – message body text (nullable)
       *   created_at – ISO datetime string
       */
      const backendPayload: GetNotificationsResponse = {
        notifications: [
          {
            id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            type: "info",
            title: "Price Alert",
            body: "Your tracked price has changed.",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await getNotifications();

      expect(result).toHaveProperty("notifications");
      expect(Array.isArray(result.notifications)).toBe(true);
      const notification = result.notifications[0]!;
      expect(notification).toHaveProperty("id");
      expect(notification).toHaveProperty("type");
      expect(notification).toHaveProperty("title");
      expect(notification).toHaveProperty("body");
      expect(notification).toHaveProperty("created_at");
      expect(typeof notification.id).toBe("string");
      expect(typeof notification.type).toBe("string");
      expect(typeof notification.title).toBe("string");
      expect(result).toHaveProperty("total");
      expect(typeof result.total).toBe("number");
    });

    it("notification count response has expected fields", async () => {
      /**
       * GET /api/v1/notifications/count
       * Backend: {"unread": <int>}
       */
      const backendPayload: GetNotificationCountResponse = { unread: 5 };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await getNotificationCount();

      expect(result).toHaveProperty("unread");
      expect(typeof result.unread).toBe("number");
      expect(Number.isInteger(result.unread)).toBe(true);
      expect(result.unread).toBeGreaterThanOrEqual(0);
    });
  });

  // ---------------------------------------------------------------------------
  // User Profile API  (GET /api/v1/users/profile, GET /api/v1/user/preferences)
  // ---------------------------------------------------------------------------
  describe("User Profile API", () => {
    it("profile response has expected fields", async () => {
      /**
       * GET /api/v1/users/profile
       * Backend model: UserProfile (api/v1/users.py)
       * Frontend interface: UserProfile (lib/api/profile.ts)
       *
       * Key fields:
       *   email                – user's email address
       *   name                 – display name (nullable)
       *   region               – region code (nullable)
       *   onboarding_completed – boolean
       */
      const backendPayload = {
        email: "test@example.com",
        name: "Test User",
        region: "us_ct",
        utility_types: ["electricity"],
        current_supplier_id: null,
        annual_usage_kwh: 8500,
        onboarding_completed: true,
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await getUserProfile();

      expect(result).toHaveProperty("email");
      expect(result).toHaveProperty("name");
      expect(result).toHaveProperty("region");
      expect(result).toHaveProperty("onboarding_completed");
      expect(typeof result.email).toBe("string");
      expect(typeof result.onboarding_completed).toBe("boolean");
    });

    it("user preferences response has expected fields", async () => {
      /**
       * GET /api/v1/user/preferences
       * Backend: user.py get_preferences → {user_id, preferences: UserPreferences}
       *
       * Preferences include: notification_enabled, auto_switch_enabled, green_energy_only, region
       */
      const backendPayload = {
        user_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        preferences: {
          region: "us_ct",
          notification_enabled: true,
          email_notifications: true,
          push_notifications: false,
          notification_frequency: "daily",
          cost_threshold: null,
          budget_limit_daily: null,
          budget_limit_monthly: null,
          auto_switch_enabled: false,
          auto_switch_threshold: null,
          preferred_suppliers: [],
          excluded_suppliers: [],
          green_energy_only: false,
          min_renewable_percentage: 0,
          peak_avoidance_enabled: false,
          preferred_usage_hours: [],
          price_alert_enabled: false,
          price_alert_below: null,
          price_alert_above: null,
          alert_optimal_windows: false,
        },
        updated_at: "2026-01-01T00:00:00Z",
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result =
        await apiClient.get<typeof backendPayload>("/user/preferences");

      expect(result).toHaveProperty("user_id");
      expect(result).toHaveProperty("preferences");
      expect(result.preferences).toHaveProperty("region");
      expect(result.preferences).toHaveProperty("notification_enabled");
      expect(result.preferences).toHaveProperty("auto_switch_enabled");
      expect(result.preferences).toHaveProperty("green_energy_only");
      expect(typeof result.preferences.notification_enabled).toBe("boolean");
      expect(typeof result.preferences.auto_switch_enabled).toBe("boolean");
      expect(typeof result.user_id).toBe("string");
    });
  });

  // ---------------------------------------------------------------------------
  // Alert API  (GET /api/v1/alerts, /alerts/history)
  // ---------------------------------------------------------------------------
  describe("Alert API", () => {
    it("alerts list response has expected fields", async () => {
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
       * NOTE: `alert_type` does NOT appear on config rows; only in history records.
       * NOTE: `threshold` field does not exist; use price_below/price_above.
       */
      const backendPayload: GetAlertsResponse = {
        alerts: [
          {
            id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            user_id: "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            region: "us_ct",
            currency: "USD",
            price_below: 0.2,
            price_above: null,
            notify_optimal_windows: true,
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await getAlerts();

      expect(result).toHaveProperty("alerts");
      expect(Array.isArray(result.alerts)).toBe(true);
      const alert = result.alerts[0]!;
      expect(alert).toHaveProperty("id");
      expect(alert).toHaveProperty("user_id");
      expect(alert).toHaveProperty("region");
      expect(alert).toHaveProperty("currency");
      expect(alert).toHaveProperty("price_below");
      expect(alert).toHaveProperty("price_above");
      expect(alert).toHaveProperty("notify_optimal_windows");
      expect(alert).toHaveProperty("is_active");
      expect(alert).toHaveProperty("created_at");
      expect(typeof alert.id).toBe("string");
      expect(typeof alert.region).toBe("string");
      expect(typeof alert.is_active).toBe("boolean");
      expect(typeof alert.notify_optimal_windows).toBe("boolean");
      expect(result).toHaveProperty("total");
      expect(typeof result.total).toBe("number");
    });

    it("alert history response has expected fields", async () => {
      /**
       * GET /api/v1/alerts/history
       * Backend: AlertService._history_row_to_dict
       *
       * History records (alert_history table) carry an alert_type field
       * that distinguishes what kind of trigger occurred.
       */
      const backendPayload: GetAlertHistoryResponse = {
        items: [
          {
            id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            user_id: "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            alert_config_id: "c3d4e5f6-a7b8-9012-cdef-012345678902",
            alert_type: "price_drop",
            current_price: 0.18,
            threshold: null,
            region: "us_ct",
            supplier: null,
            currency: "USD",
            optimal_window_start: null,
            optimal_window_end: null,
            estimated_savings: null,
            triggered_at: "2026-01-01T00:00:00Z",
            email_sent: false,
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        pages: 1,
      };
      mockFetch.mockResolvedValue(mockJsonResponse(backendPayload));

      const result = await getAlertHistory(1, 20);

      expect(result).toHaveProperty("items");
      expect(Array.isArray(result.items)).toBe(true);
      const item = result.items[0]!;
      expect(item).toHaveProperty("alert_type");
      expect(item).toHaveProperty("current_price");
      expect(item).toHaveProperty("id");
      expect(item).toHaveProperty("user_id");
      expect(typeof item.alert_type).toBe("string");
      expect(typeof item.current_price).toBe("number");
      expect(result).toHaveProperty("total");
      expect(result).toHaveProperty("page");
      expect(result).toHaveProperty("page_size");
      expect(result).toHaveProperty("pages");
      expect(typeof result.total).toBe("number");
      expect(typeof result.page).toBe("number");
    });
  });
});
