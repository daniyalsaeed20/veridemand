/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const ExportArtifactSchema = z.object({ "artifact_id": z.string(), "content_type": z.string(), "filename": z.union([z.string(), z.null()]).default(null), "status": z.enum(["available","failed","skipped"]), "warning": z.union([z.string(), z.null()]).default(null) }).strict()

