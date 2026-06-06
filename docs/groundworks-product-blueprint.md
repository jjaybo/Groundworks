# Groundworks Product Blueprint

Groundworks is a secure web-based operating system for a lawn care business. It manages customers, employees, estimates, jobs, schedules, recurring plans, photos, invoices, balances, employee time, payroll, payments, and customer self-service.

## Product Goals

- Maintain a secure employee database.
- Track potential customers from lead through first service.
- Create estimates and convert approved estimates into scheduled jobs.
- Schedule one-time and recurring services.
- Track job status from creation through completion and invoicing.
- Capture completion evidence with photos.
- Generate invoices and track balances, credits, due dates, and payments.
- Provide a customer portal with restricted account access.
- Track employee time with clock-in and clock-out controls.
- Support end-of-day cash and check settlement before employees can clock out.
- Support payroll workflows.
- Create, manage, publish, and integrate the public company website.

## User Roles

### Admin

Admins have full operational access.

- Manage employees, permissions, payroll, customers, services, plans, prices, estimates, jobs, invoices, payments, credits, and settlements.
- Verify employee cash and check settlements.
- Resolve payment discrepancies, overages, and shortages.
- View financial reports and company-level reporting.

### Employee

Employees have limited operational access.

- Add new customers and leads.
- Edit customer contact information.
- Create estimates and jobs.
- Schedule or reschedule jobs.
- Cancel jobs with required documentation.
- Add services to a job when customer approval is recorded.
- Complete jobs and upload completion photos.
- Generate invoices.
- Record payments collected by credit card, cash, or check.
- View their own time clock, assigned jobs, payment collection totals, and settlement acknowledgements.

Employees should not have broad access to company financial reporting, payroll settings, unrelated employee records, or sensitive customer financial data beyond what is needed to perform their work.

### Customer

Customers access only their own account.

- View personal profile information.
- Edit their own contact information.
- View estimates, jobs, invoices, account balance, due dates, service plans, payment history, and credits.
- Approve estimates or added services when required.

Customers cannot edit estimates, invoices, balances, credits, job status, payment records, or company-controlled account data.

### Website Visitor

Website visitors are unauthenticated public users.

- View company branding, mission statement, services, service plans, and transparent price lists.
- Request more information.
- Request an estimate.
- Create a customer account.
- Schedule eligible services directly from the website when the service does not require a custom estimate first.

Website visitors should only be able to submit public intake forms or begin account creation. They should not have access to customer, employee, job, invoice, payment, or company financial data.

## Core Workflows

### Lead and Customer Management

1. A lead is created from the website, admin entry, employee entry, phone call, or referral.
2. Lead contact details, property details, requested services, and referral source are recorded.
3. A lead can be converted into a customer.
4. Customer records include contact information, service addresses, billing details, communication preferences, referral source, account balance, credits, invoices, jobs, and plans.

### Estimates

1. An employee or admin creates an estimate for a customer or lead.
2. The estimate contains service line items, pricing, notes, property details, expiration date, and terms.
3. The customer may approve, reject, or request changes.
4. Approved estimates can be converted into jobs.

### Job Scheduling

Jobs may originate from:

- Approved estimates.
- One-time customer requests.
- Recurring service plans.
- Admin-created internal work.

Job statuses should include:

- Draft
- Scheduled
- Dispatched
- In Progress
- Pending Customer Approval
- Completed
- Cancelled
- Invoiced
- Paid

Scheduling must support assignment to one or more employees, service date, arrival window, route/order, service address, service list, internal notes, customer-visible notes, and required equipment or materials.

### Job Cancellation

Cancelling a job requires documentation.

Required fields:

- Cancelled by: Customer or Company
- Cancellation reason
- Timestamp
- User who recorded cancellation
- Optional supporting notes or files

Cancelled jobs should remain in history and should not be deleted.

### Adding Services to a Job

Employees may add services to a job only when customer approval is recorded.

Approval should capture:

- Customer name or contact method
- Approved service
- Approved price
- Approval timestamp
- Employee who recorded approval
- Optional signature, text confirmation, email confirmation, or voice authorization note

### Job Completion

To complete a job, the employee records:

- Completed services
- Completion timestamp
- Completion notes
- Before and/or after photos when required
- Issues found
- Additional customer follow-up needed
- Payment collected, if any

Photos should be attached to the job and visible to admins. Customer visibility can be configurable.

### Invoicing

Invoices can be generated from completed jobs.

Invoices should include:

- Customer and billing address
- Service address
- Job reference
- Service line items
- Discounts
- Referral credits applied
- Taxes or fees, if applicable
- Amount due
- Due date
- Payment status

Invoices are immutable after finalization except through adjustments, credits, voids, or admin-authorized corrections.

### Payments

Supported payment methods:

- Credit card through a third-party processor
- Cash
- Check

Employees may collect payment in the field and record:

- Payment amount
- Payment type
- Job or invoice paid
- Collection timestamp
- Employee who collected payment
- Check number when applicable
- Third-party transaction reference for card payments

Credit card processing should be integrated through a provider such as Stripe, Square, or another PCI-compliant service. Groundworks should store transaction references and payment status, not raw card data.

### End-of-Day Settlement

Before clocking out, each employee who collected cash or checks must complete an end-of-day payment report.

The system generates a report showing:

- Jobs completed
- Payments collected
- Cash total
- Check total
- Payment records by customer/job/invoice

The employee bundles cash and checks with the report and submits them to a designated admin.

The admin verifies:

- Actual cash received
- Actual checks received
- Expected cash total
- Expected check total
- Overage or shortage
- Notes for discrepancy

The employee must digitally acknowledge the settlement. Only after acknowledgement can the employee clock out.

### Time Clock

Employees can clock in and clock out.

Clock-out is blocked when:

- Required settlement acknowledgement is incomplete.
- Required job completion documentation is missing.
- Required payment documentation is missing.

Time records should support admin correction with audit history.

### Payroll

Payroll functionality should use approved time records and payroll settings.

Possible payroll data:

- Employee pay rate
- Overtime rules
- Pay period
- Approved hours
- Adjustments
- Deductions or reimbursements, if needed
- Payroll export or integration

Payroll access should be admin-only or restricted to payroll-authorized users.

### Recurring Service Plans

Groundworks supports discounted recurring service plans.

Supported recurrence patterns:

- Weekly
- Bi-weekly
- Every Nth day
- Monthly
- Quarterly
- Annually

Plans should include:

- Customer
- Service address
- Services included
- Discounted price
- Start date
- End date or active-until-cancelled status
- Preferred service day or time window
- Frequency
- Assigned crew or employee, if applicable
- Scheduling rules
- Pause/resume/cancel controls

Recurring plans should automatically create scheduled jobs according to customer preference and operational rules.

### Referral Credits

Customers receive a $20 account credit when someone they referred completes their first service.

Rules:

- The referred person must be a new customer.
- The credit is awarded when the referred customer's first service is completed.
- The credit is awarded regardless of service type.
- The credit is awarded even if the referred customer only uses the company once.
- Credits do not expire.
- Customers can accumulate unlimited referral credits.
- Credits reduce account balance but should not be redeemable as cash unless the business explicitly allows it.

Referral credit records should include:

- Referring customer
- Referred customer
- Triggering completed job
- Credit amount
- Award timestamp
- Status

### Website Management

Groundworks should include the capability to create and manage the public company website, not only integrate with a separate site.

Admins should be able to manage:

- Company branding, including logo, colors, business name, contact information, service areas, and social links.
- Mission statement and company story.
- Public service descriptions.
- Transparent price lists.
- Recurring service plan descriptions and pricing.
- Promotional messages, seasonal offers, and referral program messaging.
- Public pages such as home, services, pricing, about, contact, request estimate, and customer portal login.
- Search engine metadata for public pages.
- Website form routing and notification settings.

The public website should allow interested parties to:

- Request more information.
- Request an estimate.
- Create an account.
- Submit contact and property details.
- Select requested services.
- View transparent price lists before submitting a request.
- Schedule eligible services directly when pricing and availability rules allow self-scheduling.

Direct website scheduling should create a customer request, pending job, or confirmed job based on business rules. Services that require property review, custom pricing, admin approval, or customer-specific terms should create a request or estimate workflow instead of bypassing review.

Website content changes should support draft and published states so admins can prepare updates before making them public.

### Public Account Creation and Self-Scheduling

When a website visitor creates an account, the system should:

1. Verify identity and contact information.
2. Create a customer portal user.
3. Create or link a customer record.
4. Capture service address and billing details.
5. Record marketing source, referral source, or referring customer when provided.

For direct scheduling, the system should validate:

- Service availability.
- Service area eligibility.
- Transparent price or plan price.
- Customer-selected date and time window.
- Required customer approval of terms.
- Deposit or prepayment requirements, if any.
- Whether admin approval is required before confirmation.

Confirmed website-scheduled jobs should appear in the internal schedule and should be clearly marked as originating from the website.

## Data Model

Initial entities:

- User
- Role
- Permission
- Employee
- Customer
- Lead
- ServiceAddress
- Service
- ServicePlan
- Estimate
- EstimateLineItem
- Job
- JobService
- JobPhoto
- JobCancellation
- WebsitePage
- WebsiteBranding
- WebsiteContentBlock
- WebsitePriceList
- WebsiteInquiry
- WebsiteEstimateRequest
- WebsiteSchedulingRequest
- Invoice
- InvoiceLineItem
- Payment
- AccountCredit
- Referral
- TimeEntry
- Settlement
- SettlementLineItem
- DigitalSignature
- AuditLog

## Security Requirements

- Use role-based access control.
- Customers can only access records tied to their own customer account.
- Employees can only access customer and job information necessary for their assigned duties.
- Admin-only areas must include employee management, payroll, settlement verification, financial reporting, and system configuration.
- All sensitive data must be encrypted in transit using HTTPS.
- Sensitive fields should be encrypted at rest where appropriate.
- Do not store raw credit card numbers or card verification codes.
- Use a PCI-compliant payment processor for credit card handling.
- Maintain audit logs for changes to estimates, jobs, invoices, payments, settlements, employee time, payroll, customer data, and permissions.
- Require strong authentication for admins and employees.
- Consider multi-factor authentication for admin and payroll access.

## Website Management and Integration

Groundworks should provide built-in website management for the public company site and expose integration points for any existing external site.

The built-in public website should be able to:

- Display company branding, mission statement, service areas, services, recurring plans, and transparent price lists.
- Capture leads and general inquiries.
- Let prospects request more information.
- Let prospects request estimates.
- Let visitors create customer accounts.
- Let customers log into the portal.
- Let eligible customers schedule services directly.
- Show service offerings, plan options, discounts, and referral program terms.

Website-submitted data should enter Groundworks as leads or customer requests, not directly as trusted finalized jobs or invoices.

Website-scheduled services may become confirmed jobs only when they pass configured business rules for service area, price, availability, customer account status, approval, and payment requirements.

## Recommended MVP

### Phase 1: Operations Core

- Admin and employee login
- Customer and lead management
- Services catalog
- Estimate creation
- Job creation and scheduling
- Job status tracking
- Job completion photos
- Invoice generation
- Basic payment recording
- Customer portal read-only view for invoices/jobs/balance
- Public website with branding, mission statement, services, pricing, contact forms, estimate requests, and customer portal login

### Phase 2: Field Payments and Settlement

- Employee payment collection tracking
- Cash/check daily report
- Admin settlement verification
- Overage/shortage tracking
- Employee digital acknowledgement
- Clock-out blocking until settlement acknowledgement is complete

### Phase 3: Recurring Plans and Referral Credits

- Recurring plan configuration
- Automatic job generation
- Plan discounts
- Referral tracking
- Automatic $20 account credits after referred customer's first completed service
- Customer account creation from the website
- Direct website scheduling for eligible services

### Phase 4: Payroll and Advanced Financials

- Time clock approvals
- Payroll calculations
- Payroll exports or integration
- Advanced reports
- Admin financial dashboard
- Advanced website content management, promotions, SEO settings, and publishing workflows

## Open Decisions

- Which payment processor should be used for card payments?
- Should customers be able to pay invoices inside the portal?
- Should employees be able to see customer account balances or only job-level payment status?
- Are service prices fixed, estimate-based, or both?
- Do recurring plans require contracts or cancellation terms?
- Should completion photos be customer-visible by default?
- What payroll provider, if any, should Groundworks integrate with?
- What accounting system, if any, should invoices and payments sync to?
- Should jobs support crews, individual employees, or both?
- What mobile experience is required for field employees?
- Which services can be scheduled directly from the website without manual review?
- Should direct website scheduling require a deposit, full prepayment, or no upfront payment?
- Who is allowed to publish website content changes?
- Should the website support multiple locations or service areas with different pricing?
