export { summarize, payload, cents } from "/work/checks_public.mjs";

/** Whether a key is present at all (an empty or undefined discount_code must be omitted). */
export async function payloadKeys(form) {
  const { buildCreateInvoicePayload } = await import("/work/project/web/src/lib/api.ts");
  return Object.keys(buildCreateInvoicePayload(form)).sort();
}
