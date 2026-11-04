// Public checks for the web data layer. Modules are imported per call so a
// syntax error in one file fails the tests that use it, not the whole run.
const lib = (name) => import(`/work/project/web/src/lib/${name}.ts`);

export async function summarize(invoice) {
  return (await lib("invoice")).summarizeInvoice(invoice);
}

export async function payload(form) {
  return (await lib("api")).buildCreateInvoicePayload(form);
}

export async function cents(values) {
  const { formatCents } = await lib("money");
  return values.map(formatCents);
}
