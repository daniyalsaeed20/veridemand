/* AUTO-GENERATED — do not edit by hand. */
import { z } from "zod"

export const DraftSectionSchema = z.object({ "draft_id": z.string(), "heading": z.string(), "id": z.string(), "order_index": z.number().int().gte(0), "paragraphs": z.array(z.any()).optional(), "section_type": z.any() }).strict()

