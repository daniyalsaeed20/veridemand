/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const DocumentPageSchema = z.object({ "document_id": z.string(), "extraction_method": z.union([z.any(), z.null()]).default(null), "height": z.number().gt(0), "id": z.string(), "ocr_status": z.union([z.string(), z.null()]).default(null), "page_number": z.number().int().gte(1), "quality_flags": z.array(z.string()).optional(), "route": z.any(), "span_count": z.union([z.number().int().gte(0), z.null()]).default(null), "text_coverage": z.union([z.number().gte(0).lte(1), z.null()]).default(null), "token_count": z.union([z.number().int().gte(0), z.null()]).default(null), "width": z.number().gt(0) }).strict()

