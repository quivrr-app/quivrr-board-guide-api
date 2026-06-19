# Quivrr Board Guide API

Segregated backend for Quivrr Board Guide.

Working persona:
Bodhi, the Core Lord

Purpose:
- Serve the board guide chat API
- Integrate with Azure OpenAI
- Keep LLM traffic separate from quivrr-backend
- Avoid touching catalogue, inventory, MFA and market intelligence workloads in Phase 1

## Board knowledge architecture

The canonical surfboard catalogue is global. Regional manufacturer and retailer records are
availability only and are queried at recommendation time with an explicit `AU`, `EU`, or `ID`
filter.

Description precedence is:

1. Manufacturer description captured in `canonical_board_profiles.json`.
2. Quivrr-reviewed intelligence override.
3. A generated factual summary when no manufacturer description exists.

Retailer descriptions are not canonical board truth and the description scraper never reads
retailer pages. Run the manufacturer enrichment as a read-only dry run first:

```powershell
python scripts/scrape_manufacturer_board_descriptions.py --report description_audit.json
```

After reviewing coverage and samples, `--apply` updates generated JSON only. It never writes SQL.
