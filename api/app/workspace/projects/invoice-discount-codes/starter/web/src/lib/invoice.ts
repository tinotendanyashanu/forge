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
  subtotal_cents: number;
  total_cents: number;
};

export type SummaryRow = { label: string; amount: string; emphasis?: boolean };

/** Rows for the totals panel under the line items. */
export function summarizeInvoice(invoice: Invoice): SummaryRow[] {
  return [
    { label: "Subtotal", amount: formatCents(invoice.subtotal_cents) },
    { label: "Total", amount: formatCents(invoice.total_cents), emphasis: true },
  ];
}
