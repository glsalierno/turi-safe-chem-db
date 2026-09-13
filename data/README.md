# data/

Small **seed** files safe to share / commit:

| File | Role |
|------|------|
| `priority_cas_list.txt` | Priority solvent CAS list |
| `priority_expert_p2oasys_scores.csv` | Expert P2OASys Auto6 maxes |
| `fisher_catalog_by_cas.csv` | Fisher part numbers / product URLs |
| `priority_solvents_queue.csv` | Queue metadata for batch runs |

## Do not commit here

- Large harvest dumps, GHaz* trees
- `*.sofx`, HSPiP binaries
- Runtime SQLite caches (`cache/*.db`)
- Batch report CSVs with hundreds of rows (keep locally)

Override paths with `EXPERT_P2OASYS_CSV`, `P2OASYS_SCORE_LOOKUP_DB`, `HSPIP_DATA`.
