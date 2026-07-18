/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const UserDecisionSchema = z.object({ "action": z.any(), "actor_role": z.union([z.enum(["paralegal","attorney","system"]), z.null()]).default(null), "id": z.string(), "new_value": z.union([z.string(), z.record(z.any()), z.null()]).default(null), "old_value": z.union([z.string(), z.record(z.any()), z.null()]).default(null), "reason": z.union([z.string(), z.null()]).default(null), "session_id": z.string(), "target_id": z.string(), "target_type": z.enum(["fact","issue","document","span","billing","draft"]), "timestamp": z.string().datetime({ offset: true }) }).strict()

