/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const UploadRejectionSchema = z.object({ "display_name": z.string().min(1), "error_code": z.string(), "message": z.string() }).strict()

