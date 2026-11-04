from fastapi import APIRouter, HTTPException, Request, status

from invoices import repository
from invoices.models import Invoice, InvoiceIn

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_invoice(body: InvoiceIn, request: Request) -> Invoice:
    conn = request.app.state.db
    invoice_id = repository.create_invoice(conn, body)
    return repository.get_invoice(conn, invoice_id)


@router.get("/{invoice_id}")
def get_invoice(invoice_id: int, request: Request) -> Invoice:
    invoice = repository.get_invoice(request.app.state.db, invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return invoice
