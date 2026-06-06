# Invoice Template Notes

These notes summarize the paid and unpaid invoice samples provided on June 5, 2026. They are intentionally written as template requirements and avoid repeating private customer contact details.

## Header

Invoices should show:

- Company name: J&E Professional Services, LLC
- Company address
- Company phone
- Invoice title
- Customer billing block
- Service address block
- Primary contact block
- Account number
- Invoice number
- Invoice date

## Line Items

The samples use a simple line-item table:

- Item or service group
- Service name
- Service description
- Cost
- Quantity
- Price

## Totals

Invoices should show:

- Subtotal
- Discount label and amount, when applicable
- Total
- Amount paid
- Payment method, when paid
- Amount due
- Account balance
- Balance due

## Terms And Notes

Observed terms and notes from the samples:

- Payment is due on receipt.
- Thank-you note.
- Late fee note: `$5.00` late fee for invoices not paid within `10` days of completion.
- Service date.
- Next service date when applicable.
- Work notes from the job.
- Check-in and check-out times.
- Weather details, if available.

## Signatures

The samples include:

- Client signature with date.
- Tech signature with date.

## Payment Stub

The samples include a payment stub with:

- Company name and address.
- Customer name.
- Account number.
- Invoice number.
- Invoice date.
- Balance due.
- Amount enclosed.

## Paid vs. Unpaid Behavior

- A paid invoice displays amount paid and payment method.
- An unpaid or discounted invoice may still show an amount due of `$0.00` when the total is fully discounted.
- Groundworks should treat invoice payment status separately from the original job status.
- Groundworks records payments as separate records so each invoice can show payment history.

## Current Groundworks Implementation

- Groundworks now has a printable invoice detail page at `/invoices/view?id=<invoice_id>`.
- The page includes the company header, invoice metadata, customer/service blocks, line-item table, totals, terms, notes, signature lines, footer contact line, and payment stub.
- Groundworks calculates invoice due dates as `15` days after the job's service date.
- The printable invoice terms say payment is due `15` days from the date of service.
- The current implementation is web/print-first. Native PDF download should be added later.
