# Catch Me If You Scam

## Application Purpose

**Catch Me If You Scam** is a multi-agent financial fraud prevention application designed to help users identify suspicious payment requests and verify transactions before transferring money.

The application addresses scams such as phishing and impersonation, where attackers manipulate users into voluntarily sending money.

The system consists of two agents with distinct responsibilities:
- **Assistant Agent:** Represents the user, analyzes incoming messages, identifies suspicious payment requests, and communicates with the Payments Agent.
- **Payments Agent:** Represents the bank, verifies registered recipients and daily transfer limits, and provides payment execution functionality.

The application includes an A2A gateway for communication between the agents and uses MCP tools for banking operations.

Both agents are LLM-based, using Gemini 3.5 Flash Lite.

## Supported Tasks

1. **Message Analysis:** Read incoming SMS messages and identify potential fraud indicators, such as impersonation, urgency, and requests to transfer money to unfamiliar accounts.
2. **Payee Lookup:** Retrieve registered payment recipients while keeping full account numbers hidden from the Assistant Agent.
3. **Payment Verification:** Request independent verification of payment recipients and transfer amounts through the Payments Agent.
4. **Daily Limit Checking:** Check whether a requested transfer is within the remaining daily transfer limit of $1,000.
5. **Simulated Transfers:** Execute transfers in a mock banking environment. In Phase 1, strong system instructions are used to restrict transfer execution.
6. **Agent Communication:** Exchange verification requests and responses between the Assistant and Payments Agents using A2A.

## Scope

The application uses simulated SMS messages, registered payees, and banking data. It does not connect to real bank accounts or transfer real money.

In Phase 1, the application demonstrates multi-agent coordination without a dedicated policy enforcement framework. Strong system instructions are intentionally used to restrict transfer execution and focus on payment verification. However, these instructions do not guarantee that transfers cannot be executed.

In Phase 2, the application will introduce enforceable security policies at the agent communication and tool execution boundaries to prevent unauthorized transfers and unauthorized sharing of sensitive information.