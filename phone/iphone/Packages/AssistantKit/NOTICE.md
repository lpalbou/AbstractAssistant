# Gateway client

`AssistantKit` depends on the gateway client every AbstractAssistant Apple client shares,
the MIT-licensed `AbstractGatewayClient` package in
[`watch/apple/Packages/AbstractGatewayClient`](../../../../watch/apple/Packages/AbstractGatewayClient)
(see [the repository license](../../../../LICENSE)). Until backlog 1053 step 3 the iPhone kept its
own copy of that client (`PhoneGatewayClient`, a snapshot of 2026-10-19); there is no snapshot
any more: a change to a gateway route or wire model is made once, in the shared package, and
tested there with `swift test`.
