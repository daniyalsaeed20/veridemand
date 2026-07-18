/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const HealthResponseSchema = z.object({ "api_version": z.string().default("v1"), "app_version": z.union([z.string(), z.null()]).default(null), "capabilities": z.union([z.any(), z.record(z.any())]), "contracts_version": z.string().default("0.1"), "message": z.union([z.string(), z.null()]).default(null), "status": z.any(), "time_utc": z.string().datetime({ offset: true }) }).strict()

