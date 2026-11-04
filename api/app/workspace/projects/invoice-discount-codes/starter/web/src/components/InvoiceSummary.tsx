// Rendered by the web app. FORGE does not render React components; the logic
// they depend on lives in web/src/lib and is what the tests exercise.
import { summarizeInvoice, type Invoice } from "../lib/invoice.ts";

export function InvoiceSummary({ invoice }: { invoice: Invoice }) {
  return (
    <dl className="invoice-summary">
      {summarizeInvoice(invoice).map((row) => (
        <div key={row.label} className={row.emphasis ? "row total" : "row"}>
          <dt>{row.label}</dt>
          <dd>{row.amount}</dd>
        </div>
      ))}
    </dl>
  );
}
