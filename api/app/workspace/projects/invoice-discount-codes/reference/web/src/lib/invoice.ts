import { formatCents } from "./money.ts";

export type InvoiceLine = {
  id: number;
  description: string;
  quantity: number;
  unit_price_cents: number;
};

/** The invoice as returned by GET /invoices/{id}. */
export type Invoice = {
  id: number;
  customer: string;
  lines: InvoiceLine[];
  discount_code: string | null;
  subtotal_cents: number;
  discount_cents: number;
  total_cents: number;
};

export type SummaryRow = { label: string; amount: string; emphasis?: boolean };

/** Rows for the totals panel under the line items. */
export function summarizeInvoice(invoice: Invoice): SummaryRow[] {
  const rows: SummaryRow[] = [{ label: "Subtotal", amount: formatCents(invoice.subtotal_cents) }];
  if (invoice.discount_cents > 0) {
    const label = invoice.discount_code ? `Discount (${invoice.discount_code})` : "Discount";
    rows.push({ label, amount: formatCents(-invoice.discount_cents) });
  }
  rows.push({ label: "Total", amount: formatCents(invoice.total_cents), emphasis: true });
  return rows;
}
