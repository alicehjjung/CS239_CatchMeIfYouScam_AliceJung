# Requirements: fraud-guard

## 1. Overview

This application, *Catch Me If You Scam*, is a two-agent financial fraud prevention assistant designed to protect users from potentially fraudulent money transfers.

The application has two agents:

- **Assistant Agent:** Acts on the user's behalf. It reads and analyzes untrusted messages, explains potential scam indicators, and requests payment verification.
- **Payments Agent:** Acts on the bank's behalf. It checks recipients and transfer limits and can execute simulated transfers.

The system separates the Assistant Agent and the Payments Agent. The Assistant Agent cannot directly execute transfers, while the Payments Agent should receive only the information necessary to verify payment requests.

## 2. Functional Requirements (Must-Do)

The application should:

| ID | Requirement |
|---|---|
| FR-1 | Allow users to provide messages and request payment verification or money transfers. |
| FR-2 | Allow the Assistant Agent to analyze messages and explain potential indicators of scams. |
| FR-3 | Allow the Assistant Agent to send payment verification requests to the Payments Agent. |
| FR-4 | Allow the Payments Agent to check registered recipients and daily transfer limits. |
| FR-5 | Support simulated money transfers using a mock banking system. |

## 3. Security Requirements (Must-Never)

The application must never:

| ID | Requirement | Related Policy |
|---|---|---|
| MN-1 | Allow the Assistant Agent to execute money transfers directly. | P5 |
| MN-2 | Allow the Payments Agent to receive raw SMS messages or unrelated conversation content. | P6 |
| MN-3 | Execute a transfer without explicit user confirmation. | P1 |
| MN-4 | Execute a transfer to an unregistered recipient or an account originating from an untrusted message without additional verification. | P2 |
| MN-5 | Execute transfers that exceed the allowed daily transfer limit. | P3 |
| MN-6 | Expose sensitive banking information, such as account balances or full account numbers, to the Assistant Agent. | P6 |
| MN-7 | Treat instructions found inside an untrusted message as direct user instructions or automatically trust payment details originating from that message. | P1, P4 |

These are intended security requirements. Some are not yet enforced in Phase 1. Detailed policies are defined in `policy.md`.