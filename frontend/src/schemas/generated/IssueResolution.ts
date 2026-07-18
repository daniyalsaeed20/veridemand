/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const IssueResolutionSchema = z.object({ "actor": z.union([z.string(), z.null()]).default(null), "at": z.string().datetime({ offset: true }), "note": z.union([z.string(), z.null()]).default(null), "option": z.string() }).strict()

