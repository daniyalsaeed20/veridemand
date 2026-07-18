/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const PreflightFindingSchema = z.object({ "blocking": z.boolean(), "code": z.string(), "document_ids": z.union([z.array(z.string()), z.null()]).default(null), "draft_ref": z.union([z.any(), z.null()]).default(null), "fact_ids": z.union([z.array(z.string()), z.null()]).default(null), "id": z.union([z.string(), z.null()]).default(null), "issue_id": z.union([z.string(), z.null()]).default(null), "message": z.string().min(1), "semantic_label": z.union([z.any(), z.null()]).default(null), "severity": z.any(), "source_span_ids": z.array(z.string()).optional() }).strict()

