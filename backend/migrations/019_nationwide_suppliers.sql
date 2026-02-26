-- Migration 019: Nationwide supplier seeding
-- Seed supplier_registry with major utility providers for deregulated states
--
-- CT suppliers (Eversource, United Illuminating, NextEra) are already seeded.
-- This adds suppliers for other deregulated and large states.

-- Texas
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'TXU Energy', ARRAY['us_tx'], true, false, 'https://www.txu.com'),
  (gen_random_uuid(), 'Reliant Energy', ARRAY['us_tx'], true, false, 'https://www.reliant.com'),
  (gen_random_uuid(), 'Green Mountain Energy', ARRAY['us_tx'], true, true, 'https://www.greenmountainenergy.com'),
  (gen_random_uuid(), 'Direct Energy', ARRAY['us_tx'], true, false, 'https://www.directenergy.com')
ON CONFLICT DO NOTHING;

-- Ohio
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'AEP Ohio', ARRAY['us_oh'], true, false, 'https://www.aepohio.com'),
  (gen_random_uuid(), 'Duke Energy Ohio', ARRAY['us_oh'], true, false, 'https://www.duke-energy.com'),
  (gen_random_uuid(), 'FirstEnergy Ohio', ARRAY['us_oh'], true, false, 'https://www.firstenergycorp.com')
ON CONFLICT DO NOTHING;

-- Pennsylvania
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'PECO Energy', ARRAY['us_pa'], true, false, 'https://www.peco.com'),
  (gen_random_uuid(), 'PPL Electric', ARRAY['us_pa'], true, false, 'https://www.pplelectric.com'),
  (gen_random_uuid(), 'Duquesne Light', ARRAY['us_pa'], true, false, 'https://www.duquesnelight.com')
ON CONFLICT DO NOTHING;

-- Illinois
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'ComEd', ARRAY['us_il'], true, false, 'https://www.comed.com'),
  (gen_random_uuid(), 'Ameren Illinois', ARRAY['us_il'], true, false, 'https://www.ameren.com')
ON CONFLICT DO NOTHING;

-- New York
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'Con Edison', ARRAY['us_ny'], true, false, 'https://www.coned.com'),
  (gen_random_uuid(), 'National Grid NY', ARRAY['us_ny'], true, false, 'https://www.nationalgridus.com'),
  (gen_random_uuid(), 'NYSEG', ARRAY['us_ny'], true, false, 'https://www.nyseg.com')
ON CONFLICT DO NOTHING;

-- New Jersey
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'PSE&G', ARRAY['us_nj'], true, false, 'https://www.pseg.com'),
  (gen_random_uuid(), 'JCP&L', ARRAY['us_nj'], true, false, 'https://www.firstenergycorp.com'),
  (gen_random_uuid(), 'Atlantic City Electric', ARRAY['us_nj'], true, false, 'https://www.atlanticcityelectric.com')
ON CONFLICT DO NOTHING;

-- Massachusetts (Eversource already seeded for CT — add MA region + others)
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'National Grid MA', ARRAY['us_ma'], true, false, 'https://www.nationalgridus.com'),
  (gen_random_uuid(), 'Unitil', ARRAY['us_ma'], true, false, 'https://www.unitil.com')
ON CONFLICT DO NOTHING;

-- Maryland
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'BGE', ARRAY['us_md'], true, false, 'https://www.bge.com'),
  (gen_random_uuid(), 'Pepco', ARRAY['us_md', 'us_dc'], true, false, 'https://www.pepco.com'),
  (gen_random_uuid(), 'Delmarva Power', ARRAY['us_md', 'us_de'], true, false, 'https://www.delmarva.com')
ON CONFLICT DO NOTHING;

-- Michigan
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'DTE Energy', ARRAY['us_mi'], true, false, 'https://www.dteenergy.com'),
  (gen_random_uuid(), 'Consumers Energy', ARRAY['us_mi'], true, false, 'https://www.consumersenergy.com')
ON CONFLICT DO NOTHING;

-- California
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'PG&E', ARRAY['us_ca'], true, false, 'https://www.pge.com'),
  (gen_random_uuid(), 'Southern California Edison', ARRAY['us_ca'], true, false, 'https://www.sce.com'),
  (gen_random_uuid(), 'SDG&E', ARRAY['us_ca'], true, false, 'https://www.sdge.com')
ON CONFLICT DO NOTHING;

-- Florida
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'FPL (Florida Power & Light)', ARRAY['us_fl'], true, false, 'https://www.fpl.com'),
  (gen_random_uuid(), 'Duke Energy Florida', ARRAY['us_fl'], true, false, 'https://www.duke-energy.com'),
  (gen_random_uuid(), 'Tampa Electric', ARRAY['us_fl'], true, false, 'https://www.tampaelectric.com')
ON CONFLICT DO NOTHING;

-- Georgia
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'Georgia Power', ARRAY['us_ga'], true, false, 'https://www.georgiapower.com')
ON CONFLICT DO NOTHING;

-- Virginia
INSERT INTO supplier_registry (id, name, regions, is_active, green_energy_provider, website)
VALUES
  (gen_random_uuid(), 'Dominion Energy Virginia', ARRAY['us_va'], true, false, 'https://www.dominionenergy.com'),
  (gen_random_uuid(), 'Appalachian Power', ARRAY['us_va'], true, false, 'https://www.appalachianpower.com')
ON CONFLICT DO NOTHING;
