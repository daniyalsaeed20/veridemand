/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const IssueSchema = z.object({ "blocking": z.boolean(), "document_ids": z.union([z.array(z.string()), z.null()]).default(null), "explanation": z.string(), "fact_ids": z.union([z.array(z.string()), z.null()]).default(null), "id": z.string(), "issue_type": z.string(), "options": z.union([z.array(z.string()), z.null()]).default(null), "resolution": z.union([z.any(), z.null()]).default(null), "session_id": z.string(), "severity": z.any(), "source_span_ids": z.array(z.string()).optional(), "status": z.any(), "title": z.string().min(1) }).strict()

