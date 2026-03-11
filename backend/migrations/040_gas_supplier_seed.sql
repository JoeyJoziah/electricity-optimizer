-- Migration 040: Seed gas suppliers into supplier_registry
-- Gas suppliers for deregulated states. supplier_registry already supports
-- utility_types[] array (migration 006).

-- Major gas suppliers in deregulated markets
INSERT INTO supplier_registry (name, utility_types, regions, website, api_available, rating, green_energy, is_active)
VALUES
    -- National/multi-state gas suppliers
    ('Direct Energy', '{natural_gas,electricity}', '{us_ct,us_oh,us_pa,us_il,us_nj,us_md,us_de,us_ma}',
     'https://www.directenergy.com', FALSE, 4.0, FALSE, TRUE),
    ('Constellation', '{natural_gas,electricity}', '{us_ct,us_oh,us_pa,us_il,us_ny,us_nj,us_md,us_ma}',
     'https://www.constellation.com', FALSE, 4.1, TRUE, TRUE),
    ('IGS Energy', '{natural_gas,electricity}', '{us_oh,us_pa,us_il,us_md}',
     'https://www.igsenergy.com', FALSE, 3.9, TRUE, TRUE),
    ('XOOM Energy', '{natural_gas,electricity}', '{us_ct,us_oh,us_pa,us_il,us_ny,us_nj,us_md,us_de}',
     'https://www.xoomenergy.com', FALSE, 3.7, FALSE, TRUE),
    ('Infinite Energy', '{natural_gas}', '{us_ga,us_nj,us_ny}',
     'https://www.infiniteenergy.com', FALSE, 4.2, FALSE, TRUE),
    ('Georgia Natural Gas', '{natural_gas}', '{us_ga}',
     'https://www.georgianaturalgas.com', FALSE, 3.8, FALSE, TRUE),
    ('SCANA Energy', '{natural_gas}', '{us_ga}',
     'https://www.scanaenergy.com', FALSE, 4.0, FALSE, TRUE),
    ('National Grid', '{natural_gas,electricity}', '{us_ny,us_ma,us_ri}',
     'https://www.nationalgridus.com', TRUE, 3.9, FALSE, TRUE),
    ('Columbia Gas', '{natural_gas}', '{us_oh,us_pa,us_in,us_ky,us_md}',
     'https://www.columbiagasohio.com', FALSE, 3.6, FALSE, TRUE),
    ('Dominion Energy', '{natural_gas,electricity}', '{us_oh,us_pa}',
     'https://www.dominionenergy.com', FALSE, 3.8, FALSE, TRUE),
    ('Shipley Energy', '{natural_gas,heating_oil}', '{us_pa,us_md}',
     'https://www.shipleyenergy.com', FALSE, 4.3, FALSE, TRUE),
    ('Just Energy', '{natural_gas,electricity}', '{us_il,us_oh,us_pa,us_ny,us_nj}',
     'https://www.justenergy.com', FALSE, 3.5, TRUE, TRUE)
ON CONFLICT DO NOTHING;

GRANT SELECT, INSERT, UPDATE, DELETE ON supplier_registry TO neondb_owner;
