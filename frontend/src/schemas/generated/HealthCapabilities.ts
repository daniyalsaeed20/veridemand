/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const HealthCapabilitiesSchema = z.object({ "llm_semantic_extraction_enabled": z.boolean(), "max_files_per_session": z.number().int(), "max_pages_per_session": z.number().int(), "ocr_enabled": z.boolean() }).catchall(z.any())

