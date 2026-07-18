/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const UserOverrideSchema = z.object({ "at": z.string().datetime({ offset: true }), "reason": z.string(), "value": z.any() }).strict()

