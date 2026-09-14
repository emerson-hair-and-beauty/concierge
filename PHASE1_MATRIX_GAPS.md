# Product metadata audit

Read-only live audit, 2026-09-14. No index was created, deleted, or changed.
The default namespace query returned 247 records. Every returned record carried a SKU.
The live source therefore supports a SKU join. The older document totals do not describe this result.

| Category | Returned records |
|---|---:|
| Missing | 117 |
| Styler | 44 |
| Leave In | 29 |
| Cleanser | 22 |
| Deep Conditioner | 13 |
| Instant Conditioner | 12 |
| Oil | 9 |
| Treatment | 1 |

The plan path uses these exact category names. Records without a category cannot be attached to a step reliably.

The live flag vocabulary is:

`advanced_user`, `aloe`, `beginner_friendly`, `best_seller`, `butter_oil_heavy`, `cg_approved`,
`coconut`, `humectant_heavy`, `humectant_safe`, `lightweight`, `low_buildup_risk`, `protein`,
`silicone_free`, and `sulfate_free`.

The engine requires additional evidence for some states:

- Repair: `bond_builder` and `strengthening` are absent. Protein alone does not establish either property.
- Reset: `chelating` and `clarifying` are absent.
- Climate: `anti_humectant` and `humidity_shield` are absent.
- Some exclusions require explicit evidence such as `wax_free` or `mineral_oil_free`, which is also absent.

The old pipeline reranks products and can retain records that violate its preferences.
The Phase 1 path enforces the plan's hard-filter promise. It returns empty product steps when evidence is missing.
This prevents unsupported recommendations but makes matrix completion a customer-launch dependency.

Emerson must confirm missing categories and product properties in the matrix.
Engineering must then update the index from that approved source and check recommendation coverage.
The supplier's Shopify catalog sync supplies commercial fields; it does not resolve these knowledge gaps.
Do not equate unrelated flags or infer product properties from a product title to fill the gaps.

Reproduce the audit with `python scripts/phase1_preflight.py`.
