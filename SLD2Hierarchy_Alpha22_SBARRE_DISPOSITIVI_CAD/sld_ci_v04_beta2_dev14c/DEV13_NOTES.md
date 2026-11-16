# DEV13 — explicit interposed-device topology edges

Dev13 extends dev12 without changing blind behavior.

- `INTERPOSED_DEVICE` operator reviews are **not conductive bridges**.
- They are modeled as explicit structural-topology edges between the reviewed graph terminals.
- Device operating state remains separate (`UNKNOWN` unless explicitly known).
- Feeder topology verification may traverse the device as an equipment element.
- Conductive adjacency is retained separately from structural topology adjacency.
- No change occurs when no interposed-device review is present.

New diagnostics:
- `modeled_interposed_device_count`
- `added_device_topology_edge_count`
- summary equivalents prefixed with `operator_`

This implements the distinction:
`same conductor` != `device between terminals` != `unresolved`, while allowing the feeder route to continue through a real device without bypassing it.
