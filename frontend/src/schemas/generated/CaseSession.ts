/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const CaseSessionSchema = z.object({ "created_at": z.string().datetime({ offset: true }), "expires_at": z.string().datetime({ offset: true }), "id": z.string(), "last_activity_at": z.string().datetime({ offset: true }), "settings": z.record(z.any()).optional(), "status": z.any(), "warning": z.union([z.string(), z.null()]).default(null) }).strict()

