# Alpha 7 — lettura dei report

La nuova diagnostica distingue rigorosamente:

- `tag`: identità testuale rilevata, NON dispositivo fisico certificato.
- `symbol_hypotheses`: una o più forme geometriche candidate, con due `circle_drawing_ids` sorgente.
- `possible_contacts_unverified`: segmenti solidi che sembrano raggiungere la forma, con `source_stroke_id` e coordinate; non equivalgono a terminali né a conduttori accettati.
- `drawing_note_cues`: contesto testuale di rimandi ad altre tavole (es. FIELD MET STATION / SEE SHEET), non collegamento elettrico.
- `SAME_SYMBOL_CANDIDATE_FOR_MULTIPLE_TAGS`: collisione conservata per revisione umana, non risolta arbitrariamente.
- `PAGINE CAMPIONATE`: il modulo analizza solo il numero di pagine/ROI consentito dal budget; nessun richiamo completo se manca coverage.

I contatori di `graph_verified_feeder_memberships`, `through_device_paths_verified`, `terminals_verified` rimangono **0**. L'obiettivo raggiunto è l'individuazione auditabile di ipotesi visive da cui partire con il riconoscimento delle celle e dei terminali, non la validazione di connettività.
