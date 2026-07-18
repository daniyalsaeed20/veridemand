/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const DraftParagraphSchema = z.object({ "contains_argument": z.boolean().default(false), "id": z.string(), "support_label": z.union([z.any(), z.null()]).default(null), "supporting_fact_ids": z.array(z.string()).optional(), "text": z.string(), "verification_required": z.boolean().default(false) }).strict()

