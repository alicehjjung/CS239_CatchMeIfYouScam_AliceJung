# Tools

The application **Catch me if you scam** uses MCP tools and agent-to-agent (A2A) communication to support message analysis and payment verification.

## Assistant Agent Tools

### `read_inbox`

Reads messages in the user's inbox.

- **Input:** None.
- **Output:** A dictionary containing messages loaded from the inbox.

### `list_payees`

Lists payees without exposing full account numbers.

- **Input:** None.
- **Output:** A dictionary containing payees, including:
  - Payee ID.
  - Name of the registered recipient.
  - Masked account number showing only the last four digits.

### `request_payment_verification`

Asks the independent Payments Agent to verify a payment request through A2A communication.

- **Input:** Payment verification request text.
- **Output:** The response returned by the Payments Agent when verification succeeds.
- **Errors:** Returns an error when the request is empty or A2A communication fails.

> This tool is intended for verification only and does not directly execute transfers.

## Payments Agent Tools

### `lookup_recipient`

Checks whether a recipient is registered.

- **Input:** Recipient ID.
- **Output:**
  - Whether the recipient is registered.
  - `recipient_id`.
  - `name`: The recipient's name.

### `check_daily_limit`

Checks whether the requested amount is within the remaining daily limit.

- **Input:** Requested amount.
- **Output:**
  - Requested amount
  - Remaining limit: Daily limit minus the amount already transferred that day.
  - `allowed`: Whether the amount is positive and does not exceed the remaining limit.

### `execute_transfer`

Executes a simulated transfer in the mock banking system.

- **Input:** Recipient and amount.
- **Output on success:**
  - Transaction ID.
  - `to_account`: Destination account number.
  - `registered_payee`: Whether the recipient matches a registered payee.
  - `amount`: Transferred amount.
  - `status`: Completed.
- **Output on failure:**
  - `status`: `failed`.
  - `reason`: `invalid_amount` or `insufficient_funds`.
