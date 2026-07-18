/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const TimelineEventSchema = z.object({ "date_precision": z.union([z.enum(["exact","approximate","unknown"]), z.null()]).default(null), "event_date": z.union([z.string(), z.null()]).default(null), "event_time": z.union([z.string(), z.null()]).default(null), "event_type": z.any(), "fact_ids": z.array(z.string()).optional(), "id": z.string(), "provider_name": z.union([z.string(), z.null()]).default(null), "session_id": z.string(), "sort_key": z.union([z.string(), z.null()]).default(null), "summary": z.string() }).strict()

