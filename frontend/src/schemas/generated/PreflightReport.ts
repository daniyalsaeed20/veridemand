/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const PreflightReportSchema = z.object({ "created_at": z.string().datetime({ offset: true }), "draft_id": z.string(), "findings": z.array(z.any()).optional(), "id": z.string(), "programmatic_gate": z.enum(["pass","blocked"]), "semantic_error": z.union([z.string(), z.null()]).default(null), "semantic_ran": z.union([z.boolean(), z.null()]).default(null), "session_id": z.string() }).strict()

