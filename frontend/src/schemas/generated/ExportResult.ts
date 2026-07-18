/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const ExportResultSchema = z.object({ "created_at": z.string().datetime({ offset: true }), "docx": z.any(), "draft_id": z.string(), "export_id": z.string(), "kind": z.any(), "pdf_preview": z.union([z.any(), z.null()]).default(null), "preflight_id": z.string(), "session_id": z.string() }).strict()

