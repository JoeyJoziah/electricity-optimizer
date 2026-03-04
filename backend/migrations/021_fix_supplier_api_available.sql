-- Migration 021: Fix supplier api_available flag
-- Bug: Supplier registry endpoint filters on api_available=true, but seeds never set it.
-- This sets api_available=true for all active suppliers so the dropdown populates.

UPDATE supplier_registry SET api_available = true WHERE is_active = true;
