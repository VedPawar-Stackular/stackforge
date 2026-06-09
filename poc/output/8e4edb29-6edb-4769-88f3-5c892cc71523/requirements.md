# CareFlow Platform 2026 — Functional Requirements & User Needs

> **SDLC Category:** `requirements`  |  **Generated:** 2026-06-08 15:19

---

## Functional Requirements

### Multi-factor auth

System must implement multi-factor authentication for providers, administrators, and compliance roles

- **Confidence:** 100%
- **Type:** functional

### Provider availability

System must expose provider availability in 15-minute slots

- **Confidence:** 100%
- **Type:** functional

### Double-booking prevention

System must prevent double-booking through optimistic locking

- **Confidence:** 100%
- **Type:** functional

### Reminder dispatch

System must dispatch reminders via SMS and email with retry mechanism

- **Confidence:** 100%
- **Type:** functional

### Patient cancellation

Patients can cancel/reschedule up to 24 hours in advance

- **Confidence:** 100%
- **Type:** functional

### Telehealth video module

System must support telehealth video sessions using Twilio with quality indicators and recording requirements

- **Confidence:** 100%
- **Type:** functional

### Audit logs

System must maintain audit logs for 7 years

- **Confidence:** 100%
- **Type:** functional

### Immutable audit records

System must create immutable audit records for all PHI access events

- **Confidence:** 100%
- **Type:** functional

### Elasticsearch query

System must write audit records to Elasticsearch with a write-once index policy and allow Compliance Officers to query audit logs by multiple criteria

- **Confidence:** 100%
- **Type:** functional

### Reminder System

Send 2 automatic touches via SMS to reduce no-shows

- **Confidence:** 100%
- **Type:** functional

### Waitlist Engine

Check for available patients after cancellation

- **Confidence:** 100%
- **Type:** functional

### Integration with Athena

Update appointment status in 2 phases

- **Confidence:** 100%
- **Type:** functional

### Single-tap Join Link

Simple and streamlined patient joining process

- **Confidence:** 100%
- **Type:** functional

### Patient Chart Access

Access patient charts without window switching

- **Confidence:** 100%
- **Type:** functional

### Annotated Images

Allow providers to annotate images

- **Confidence:** 100%
- **Type:** functional

### Real-time Estimated Wait Times

Display accurate wait times for patients

- **Confidence:** 100%
- **Type:** functional

### Accurate Billing Timestamps

Record accurate billing timestamps for sessions

- **Confidence:** 100%
- **Type:** functional

### Patient Consent

Obtain explicit patient consent for recording sessions

- **Confidence:** 100%
- **Type:** functional

### Automated Reminders

Implement automated reminders via SMS to reduce no-shows

- **Confidence:** 100%
- **Type:** functional

### Real-time Waitlists

Develop real-time waitlists for efficient slot allocation

- **Confidence:** 100%
- **Type:** functional

### CareFlow-Athena Integration

Integrate CareFlow with Athena via webhook for seamless appointment updates

- **Confidence:** 100%
- **Type:** functional

### Patient Chart Access

Allow patient chart access without switching windows

- **Confidence:** 100%
- **Type:** functional

### Video Conferencing

Provide HIPAA-compliant video conferencing

- **Confidence:** 100%
- **Type:** functional

### Image Annotation

Enable annotation of medical images

- **Confidence:** 100%
- **Type:** functional

### Patient Joining Process

Implement a simple patient joining process with SMS link

- **Confidence:** 100%
- **Type:** functional

### Billing Timestamps

Generate accurate billing timestamps with session start and end

- **Confidence:** 100%
- **Type:** functional

### Patient Dashboard

Provide patient dashboard for workflow management

- **Confidence:** 100%
- **Type:** functional

### Provider Dashboard

Provide provider dashboard for workflow management

- **Confidence:** 100%
- **Type:** functional

### Telehealth Video

Implement telehealth video module

- **Confidence:** 100%
- **Type:** functional

### Automated Reminders

Send automated reminders to reduce no-show rates

- **Confidence:** 100%
- **Type:** functional

### RESTful API

Provide RESTful API layer for EHR integration

- **Confidence:** 100%
- **Type:** functional

### Post-Launch Warranty

Provide post-launch warranty for 12 months with P1/P2 bug fix

- **Confidence:** 100%
- **Type:** functional

### EHR Integration

Enable integration with existing EHR (Athena Health API v2)

- **Confidence:** 100%
- **Type:** functional

### Clinical Communications

Eliminate reliance on Microsoft Teams for clinical communications

- **Confidence:** 100%
- **Type:** functional

### Legacy Data Export

Legacy data export by Week 25

- **Confidence:** 100%
- **Type:** functional

### Athena Health API Credentials

Athena Health API credentials by Week 5

- **Confidence:** 100%
- **Type:** functional

### HIPAA BAA Execution

HIPAA BAA executed with Twilio and AWS by Week 8

- **Confidence:** 100%
- **Type:** functional

### Dedicated Product Owner

Dedicated Product Owner provided by MediConnect

- **Confidence:** 100%
- **Type:** functional

### Post-Launch Warranty

Post-launch warranty and SLAs

- **Confidence:** 100%
- **Type:** functional

### Seamless Chart Access

Provide seamless chart access during telehealth calls

- **Confidence:** 90%
- **Type:** functional

### Patient Vitals Dashboard

Provide real-time patient vitals dashboard for providers during telehealth sessions

- **Confidence:** 90%
- **Type:** functional

### Appointment No-Show Rate

Achieve an appointment no-show rate of 10% or less

- **Confidence:** 90%
- **Type:** functional

### Admin Overhead Reduction

Reduce per-provider admin overhead by 40% or more

- **Confidence:** 90%
- **Type:** functional

### Consolidate Workflows

Consolidate patient-facing and provider-facing workflows into a single application

- **Confidence:** 90%
- **Type:** functional

### Automate Processes

Automate the reminder and waitlist processes

- **Confidence:** 80%
- **Type:** functional

### Automate Scheduling

Automate the scheduling workflow to reduce manual effort

- **Confidence:** 80%
- **Type:** functional

### Reminder System

Implement a reminder system to reduce no-show appointments

- **Confidence:** 80%
- **Type:** functional

### Real-time Waitlist

Implement a real-time waitlist with integration to Athena

- **Confidence:** 80%
- **Type:** functional

### Integration with Athena

Integrate with Athena for appointment status updates

- **Confidence:** 80%
- **Type:** functional

### Patient Chart Integration

Integrate patient charts into the call window

- **Confidence:** 80%
- **Type:** functional

### Simple Patient Flow

Implement a simple patient joining process within 30 seconds

- **Confidence:** 80%
- **Type:** functional

### Estimated Wait Times

Provide estimated wait times for delayed appointments

- **Confidence:** 80%
- **Type:** functional

### Accurate Billing

Ensure accurate billing timestamps

- **Confidence:** 80%
- **Type:** functional

### Post-Launch Support

Provide 12-month post-launch support SLA

- **Confidence:** 80%
- **Type:** functional

### Defect Remediation

Provide 12-month post-launch warranty for defect remediation

- **Confidence:** 80%
- **Type:** functional

### Change Management

Any change to scope, timeline, or cost requires a signed Change Order (CO) before work begins

- **Confidence:** 80%
- **Type:** functional

### Audit Trail

Implement a centralized audit trail using Elasticsearch for logging access events

- **Confidence:** 80%
- **Type:** functional

### Clinical Communications

Eliminate Microsoft Teams for clinical communications

- **Confidence:** 80%
- **Type:** functional

### EHR Integration

Integrate with existing Electronic Health Record (EHR) system, specifically Athena Health API v2

- **Confidence:** 80%
- **Type:** functional

### Patient Management

Manage patient information and telehealth services

- **Confidence:** 80%
- **Type:** functional

### Telehealth Integration

Modify CareFlow for telehealth integration, focusing on top three requirements

- **Confidence:** 70%
- **Type:** functional

## Non-Functional Requirements

### Uptime SLA

Ensure 99.9% uptime SLA by week 8

- **Confidence:** 100%
- **Type:** non functional

### PHI Encryption

Encrypt PHI at go-live

- **Confidence:** 100%
- **Type:** non functional

### Complete Processing

Ensure complete and accurate processing by week 12

- **Confidence:** 100%
- **Type:** non functional

### Privacy Notice

Provide privacy notice and consent by week 16

- **Confidence:** 100%
- **Type:** non functional

### Session timeout

System must invalidate sessions after 15 minutes of inactivity

- **Confidence:** 100%
- **Type:** non functional

### Late-cancel flag

System must flag late-cancellations within 24 hours on patient record

- **Confidence:** 100%
- **Type:** non functional

### Secure messaging

System must implement secure messaging with encryption, attachment limits, and archival

- **Confidence:** 100%
- **Type:** non functional

### Query result export

System must allow export of query results as CSV

- **Confidence:** 100%
- **Type:** non functional

### Query result timing

System must return query results within 5 seconds

- **Confidence:** 100%
- **Type:** non functional

### Real-time Waitlist

Automated backfill for available time slots

- **Confidence:** 100%
- **Type:** non functional

### HIPAA Compliance

Ensure HIPAA compliance for calls and patient data

- **Confidence:** 100%
- **Type:** non functional

### Data Encryption

Store recordings encrypted at rest on S3

- **Confidence:** 100%
- **Type:** non functional

### Compliance

Address compliance concerns through secure messaging and centralized audit trail

- **Confidence:** 100%
- **Type:** non functional

### HIPAA Compliance

Comply with HIPAA requirements for PHI processing as a Covered Entity

- **Confidence:** 100%
- **Type:** non functional

### SOC 2 Certification

Meet SOC 2 Type II certification within 15 months

- **Confidence:** 100%
- **Type:** non functional

### PHI Transmission Security

Use TLS 1.3 for secure PHI transmission

- **Confidence:** 100%
- **Type:** non functional

### BAAs for Sub-processors

Require BAAs for sub-processors handling PHI

- **Confidence:** 100%
- **Type:** non functional

### Access Controls

Implement logical and physical access controls by month 3

- **Confidence:** 100%
- **Type:** non functional

### HIPAA Compliance

Ensure all components of the system are compliant with HIPAA regulations

- **Confidence:** 100%
- **Type:** non functional

### Data Security

Encrypt data storage, particularly in S3, and maintain secure data residency within US soil

- **Confidence:** 100%
- **Type:** non functional

### Explicit Patient Consent

Obtain explicit patient consent for recordings

- **Confidence:** 100%
- **Type:** non functional

### Encrypted Recordings

Store encrypted recordings in S3

- **Confidence:** 100%
- **Type:** non functional

### Centralized Auditing

Maintain a centralized Elasticsearch audit log for PHI access events

- **Confidence:** 100%
- **Type:** non functional

### Secure Messaging

Implement secure in-app messaging under Twilio HIPAA BAA

- **Confidence:** 100%
- **Type:** non functional

### HIPAA Compliance

Achieve HIPAA compliance and pass third-party audit

- **Confidence:** 100%
- **Type:** non functional

### Role-Based Access

Implement role-based access control for security

- **Confidence:** 100%
- **Type:** non functional

### Administrative Overhead

Reduce per-provider administrative overhead by ≥40% within 6 months

- **Confidence:** 100%
- **Type:** non functional

### No-Show Rate

Reduce appointment no-show rate from 22% to ≤10% via automated reminders

- **Confidence:** 100%
- **Type:** non functional

### System Uptime

Achieve 99.9% monthly uptime

- **Confidence:** 100%
- **Type:** non functional

### Recovery Time Objective

Recovery Time Objective (RTO) of 4 hours

- **Confidence:** 100%
- **Type:** non functional

### Recovery Point Objective

Recovery Point Objective (RPO) of 1 hour

- **Confidence:** 100%
- **Type:** non functional

### HIPAA Compliance

Achieve HIPAA compliance and pass third-party audit within 90 days

- **Confidence:** 100%
- **Type:** non functional

### Administrative Overhead Reduction

Reduce per-provider administrative overhead by ≥40%

- **Confidence:** 100%
- **Type:** non functional

### Appointment No-Show Rate Reduction

Reduce appointment no-show rate from 22% to ≤10%

- **Confidence:** 100%
- **Type:** non functional

### HIPAA Compliance

Ensure the application is HIPAA-compliant

- **Confidence:** 90%
- **Type:** non functional

### Uptime Guarantee

Provide 99.9% uptime guarantee

- **Confidence:** 90%
- **Type:** non functional

### Recovery Point Objective

Achieve 1-hour recovery point objective (RPO)

- **Confidence:** 90%
- **Type:** non functional

### Recovery Time Objective

Achieve 4-hour recovery time objective (RTO)

- **Confidence:** 90%
- **Type:** non functional

### Monthly Uptime

Achieve 99.9% monthly uptime

- **Confidence:** 90%
- **Type:** non functional

### HIPAA Compliance

Ensure HIPAA compliance for protected health information (PHI) discussions

- **Confidence:** 80%
- **Type:** non functional

### Patient Consent

Require explicit patient consent for recording sessions

- **Confidence:** 80%
- **Type:** non functional

### Data Residency

Restrict data residency to the US

- **Confidence:** 80%
- **Type:** non functional

### Administrative Overhead

Reduce provider administrative overhead by ≥40% within 6 months

- **Confidence:** 80%
- **Type:** non functional

### Security Requirements

Implement a 15-minute idle timeout with multi-factor authentication for clinical roles

- **Confidence:** 80%
- **Type:** non functional

### Appointment No-Show Rates

Reduce appointment no-show rates

- **Confidence:** 70%
- **Type:** non functional

### Patient Experience

Improve patient experience through seamless patient flow

- **Confidence:** 70%
- **Type:** non functional

### System Performance

Ensure the system can handle the workload and provide timely responses

- **Confidence:** 60%
- **Type:** non functional

### System Security

Ensure the system is secure and compliant with relevant regulations

- **Confidence:** 60%
- **Type:** non functional

### System Usability

Ensure the system is user-friendly and easy to use

- **Confidence:** 60%
- **Type:** non functional

## Constraints

### Data Residency

Enforce data residency with AWS US-based deployment

- **Confidence:** 100%
- **Type:** constraint

### API Credentials

No shared credentials allowed for Athena API

- **Confidence:** 100%
- **Type:** constraint

### Timeline

Action items due in the next few weeks

- **Confidence:** 100%
- **Type:** constraint

### Data Residency

Store data in US with AWS us-west-2 and us-east-1

- **Confidence:** 100%
- **Type:** constraint

### Athena API Credentials

Obtain Athena API v2 sandbox credentials by June 27

- **Confidence:** 100%
- **Type:** constraint

### Twilio HIPAA Timeline

Confirm Twilio HIPAA BAA process timeline by May 17

- **Confidence:** 100%
- **Type:** constraint

### Workshop Schedule

Schedule Workshop 4 by the Week of May 26

- **Confidence:** 100%
- **Type:** constraint

### HIPAA Audit Timeline

Pass third-party audit within 90 days

- **Confidence:** 100%
- **Type:** constraint

### Project Budget

Total project budget is $1,850,000

- **Confidence:** 100%
- **Type:** constraint

### Project Timeline

Total project duration is 32 weeks

- **Confidence:** 100%
- **Type:** constraint

### Project Timeline

Total project duration is 32 weeks

- **Confidence:** 100%
- **Type:** constraint

### Payment Schedule

Payment schedule of $1,850,000

- **Confidence:** 100%
- **Type:** constraint

### Business Associate Agreement

HIPAA Business Associate Agreement must be executed with Twilio and AWS by Week 8

- **Confidence:** 90%
- **Type:** constraint

### Project Budget

The total project cost is $1,850,000

- **Confidence:** 90%
- **Type:** constraint

### Project Timeline

The project must be completed within 32 weeks, from June 10, 2026 to January 29, 2027

- **Confidence:** 90%
- **Type:** constraint

### Athena API Credentials

Obtain Athena API credentials by June 27th

- **Confidence:** 80%
- **Type:** constraint

### Athena API Sandbox

Obtain Athena API v2 sandbox credentials by June 27th

- **Confidence:** 80%
- **Type:** constraint

### Data Migration Workshop

Schedule a data migration workshop by May 27th

- **Confidence:** 80%
- **Type:** constraint

### Twilio HIPAA BAA

Confirm Twilio HIPAA BAA process timeline by May 17th

- **Confidence:** 80%
- **Type:** constraint

### Telehealth UX Wireframes

Deliver low-fidelity telehealth UX wireframes by May 21st

- **Confidence:** 80%
- **Type:** constraint

### Sample Scheduling Data

Provide sample scheduling data (3 months) by May 22nd

- **Confidence:** 80%
- **Type:** constraint

## Assumptions

### HIPAA BAA Process

Twilio's HIPAA BAA process timeline will be confirmed

- **Confidence:** 70%
- **Type:** assumption

### US Data Residency

Assume data residency within US soil, with no PHI transit outside the US

- **Confidence:** 70%
- **Type:** assumption

### Athena API Availability

Assume Athena API will be available and functional

- **Confidence:** 60%
- **Type:** assumption

### Data Quality

Assume data provided will be accurate and complete

- **Confidence:** 60%
- **Type:** assumption
