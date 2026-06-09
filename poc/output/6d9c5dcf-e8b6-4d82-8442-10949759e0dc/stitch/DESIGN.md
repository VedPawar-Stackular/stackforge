---
# Project Design System: CareFlow Platform 2026 V3

## Overview
The CareFlow Platform 2026 V3 is a redesign of the existing care platform, aiming to improve usability and patient experience. This design system outlines the design principles, components, and tokens that will be applied across the platform.

## Design Principles

- Clean and professional design to convey trust and reliability
- Simple and intuitive navigation to reduce cognitive load
- Emphasis on clear and concise communication to ensure patient understanding

## Colors

- Primary color: #3A86FF
- Secondary color: #F7F7F7 (background)
- Accent color: #FF69B4 (call-to-action buttons)
- Error color: #FF3737 (error messages and warnings)

## Typography

- Base font size: 16px
- Font family: Open Sans (for a clean and professional look)
- Headings:
  - H1: 24px, bold
  - H2: 18px, medium
  - H3: 14px, regular

## Screens

### Patient Join Screen (patient_join, desktop)

The patient join screen should display a clear and concise message instructing patients on how to join the platform. This should be accompanied by a single-tap link to facilitate seamless joining.

#### Patient Join Screen Components

- **Header**: Contains the CareFlow logo and a navigation menu ( hidden on desktop, visible on mobile)
- **Join Instructions**: Clearly communicates the steps for joining the platform
- **Single-Tap Link**: A prominent call-to-action (CTA) button that patients can tap to join the platform
- **Background Image**: A soothing background image to reduce visual noise

#### Design Tokens

- **Color**: #3A86FF (primary), #F7F7F7 (background), #FF69B4 (CTA)
- **Typography**: Open Sans, 16px, regular
- **Spacing**: 24px (header-to-join-instructions), 12px (join-instructions-to-link)

### Verification Success Screen (verification_success, desktop)

The verification success screen should display a clear and concise message communicating to patients that their information has been successfully verified.

#### Verification Success Screen Components

- **Header**: Contains the CareFlow logo
- **Verification Message**: Clearly communicates that the patient's information has been successfully verified
- **Call-to-Action (CTA)**: A button that patients can click to proceed to the next step
- **Background Image**: A soothing background image to reduce visual noise

#### Design Tokens

- **Color**: #3A86FF (primary), #F7F7F7 (background), #FF69B4 (CTA)
- **Typography**: Open Sans, 16px, regular
- **Spacing**: 24px (header-to-verification-message), 12px (verification-message-to-CTA)