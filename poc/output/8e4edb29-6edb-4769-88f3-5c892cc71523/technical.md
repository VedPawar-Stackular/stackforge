# CareFlow Platform 2026 — Technical Architecture & Infrastructure

> **SDLC Category:** `technical`  |  **Generated:** 2026-06-08 15:19

---

## Functional Requirements

### Simple Patient Join Flow

Implement single-tap join link via SMS for patients

- **Confidence:** 90%
- **Type:** functional

### Session Management

Provide session management functionality

- **Confidence:** 90%
- **Type:** functional

### Image Annotation

Annotate images in real-time during telehealth calls

- **Confidence:** 90%
- **Type:** functional

### Scheduling Automation

Automate scheduling workflow to reduce 45-minute daily process

- **Confidence:** 90%
- **Type:** functional

### Reminder System

Implement reminder system to alert patients of appointments

- **Confidence:** 90%
- **Type:** functional

### Waitlist Management

Create real-time waitlist for patients who have requested a specific slot or provider

- **Confidence:** 90%
- **Type:** functional

### Recording Functionality

Provide recording functionality with patient consent

- **Confidence:** 90%
- **Type:** functional

### Clinical Time Logging

Provide clinical time logging functionality

- **Confidence:** 90%
- **Type:** functional

### Accurate Billing Timestamps

Provide accurate billing timestamps, including provider-joined-at, patient-joined-at, and session-ended-at

- **Confidence:** 90%
- **Type:** functional

### Automated Reminders

Send automated reminders via SMS to patients 48 hours and 2 hours before appointment

- **Confidence:** 90%
- **Type:** functional

## Non-Functional Requirements

### Geo-Restriction

Implement geo-restriction to US only using CloudFront

- **Confidence:** 90%
- **Type:** non functional

### Data Residency

Ensure data residency on US soil with geo-restricted CloudFront

- **Confidence:** 90%
- **Type:** non functional

### Secure Messaging

Ensure secure in-app messaging and centralized audit trail

- **Confidence:** 90%
- **Type:** non functional

### HIPAA Compliance

Ensure HIPAA compliance for PHI discussions

- **Confidence:** 90%
- **Type:** non functional

### Revenue Loss Reduction

Mitigate revenue loss due to patient no-shows

- **Confidence:** 90%
- **Type:** non functional

### HIPAA Compliance

Achieve HIPAA compliance for the application

- **Confidence:** 90%
- **Type:** non functional

### No PHI Caching

Ensure no PHI is cached at the edge

- **Confidence:** 90%
- **Type:** non functional

### Real-time Data

Ensure real-time data updates for waitlist and appointment status

- **Confidence:** 80%
- **Type:** non functional

## Constraints

### AWS Deployment

Deploy on AWS in us-west-2 and us-east-1

- **Confidence:** 90%
- **Type:** constraint
