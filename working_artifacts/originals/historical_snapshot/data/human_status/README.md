# Human-status files

The structured/binary workbook contains the frozen 72 human labels. The CSV export preserves the workbook’s blinded presentation, while the separate key maps each annotation ID to its system and pair after unblinding.

The raw-metadata workbook and CSV are templates: all 36 human-label cells are blank. They are retained because they document the response/evidence presentation and annotation IDs, but they do not support reconstruction of the reported 34/36 aggregate.

If the original completed raw-metadata labels are recovered, save them as `raw_metadata_labels_completed_36.csv` without modifying annotation IDs or order, record provenance and a checksum, and extend the quick analyzer only after confirming that the file is the original frozen annotation.

