/** What the "New invoice" form holds: raw strings from inputs. */
export type InvoiceForm = {
  customer: string;
  lines: { description: string; quantity: string; unitPrice: string }[];
  discountCode?: string;
};

/** The request body for POST /invoices. */
export type CreateInvoicePayload = {
  customer: string;
  lines: { description: string; quantity: number; unit_price_cents: number }[];
  discount_code?: string;
};

export function buildCreateInvoicePayload(form: InvoiceForm): CreateInvoicePayload {
  const payload: CreateInvoicePayload = {
    customer: form.customer.trim(),
    lines: form.lines.map((line) => ({
      description: line.description.trim(),
      quantity: Number(line.quantity),
      unit_price_cents: Math.round(Number(line.unitPrice) * 100),
    })),
  };
  const code = form.discountCode?.trim().toUpperCase();
  if (code) payload.discount_code = code;
  return payload;
}
