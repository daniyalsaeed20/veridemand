/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const ErrorEnvelopeSchema = z.object({ "details": z.record(z.any()).optional(), "error_code": z.union([z.any(), z.string()]), "message": z.string(), "request_id": z.union([z.string(), z.null()]).default(null) }).strict()

