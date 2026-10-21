# BRD excerpt — Fund Transfer (NovaPay)

**Source:** written by QualiFlow against the real running app
(`D:\AutomationTool\novapay`), not read off its code in isolation — this
describes the intended business rule, not necessarily its current
implementation. See `openapi.yaml`'s per-endpoint notes for verified gaps
between this rule and the actual `/api/transfers` behavior.

> A customer may transfer funds between their own NovaPay accounts. The
> transfer must specify a source account, a destination account, and a
> positive amount. The source and destination accounts must be different,
> and the source account must belong to the customer initiating the
> transfer. The transfer is rejected if the source account's available
> balance is less than the requested amount. On success, the source
> account is debited and the destination account is credited by the same
> amount in a single atomic operation, and a unique reference number
> (format `TRF-YYYYMMDD-XXXXXX`) is generated and returned to the
> customer. Both the debit and credit must be recorded as individual
> transaction history entries against their respective accounts.
