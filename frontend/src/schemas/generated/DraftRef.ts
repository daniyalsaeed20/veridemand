/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const DraftRefSchema = z.object({ "paragraph_id": z.string(), "sentence_index": z.union([z.number().int(), z.null()]).default(null) }).strict()

