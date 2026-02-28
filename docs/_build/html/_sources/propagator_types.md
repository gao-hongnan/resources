# Understanding Propagator Types in Distributed Tracing

## 1. W3C TraceContext (TRACECONTEXT)

### What It Is

The TraceContext propagator transmits trace identification information between
services using standardized HTTP headers: `traceparent` and `tracestate`.

### How It Works

When Service A calls Service B:

1. Service A adds a `traceparent` header to its HTTP request
2. Service B extracts this header and knows it should continue the same trace

### Example Header

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
              │  │                             │                │
              │  │                             │                └ Trace flags (sampling decision)
              │  │                             └ Parent span ID (16 hex digits)
              │  └ Trace ID (32 hex digits)
              └ Version
```

### Code Example

```python
# Service A: Sending a request
with telemetry.start_as_current_span("process_order") as span:
    # Make HTTP request to Service B
    headers = {}
    telemetry.inject_context(headers)  # Adds traceparent header
    # headers now contains: {'traceparent': '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01'}
    response = requests.get("http://service-b/api/check", headers=headers)

# Service B: Receiving the request
def handle_request(request_headers):
    # Extract the propagated context (gets trace/span IDs from traceparent)
    context = telemetry.extract_context(request_headers)

    # Start a new span as child of the received context
    with telemetry.start_as_current_span("check_inventory", context=context) as span:
        # This span is now connected to the trace started in Service A
        return {"status": "in_stock"}
```

## 2. W3C Baggage (BAGGAGE)

### What It Is

Baggage allows you to attach arbitrary key-value pairs to the trace context,
making application-specific data available across service boundaries.

### How It Works

When Service A needs to send business context to Service B:

1. Service A adds a `baggage` header with key-value pairs
2. Service B extracts these values and can use them for business logic or add
   them as span attributes

### Example Header

```
baggage: user_id=42,transaction_id=abc123,priority=high
```

### Code Example

```python
# Service A: Setting and propagating baggage
# First, add values to the current baggage
from opentelemetry.baggage import set_baggage

set_baggage("user_id", "42")
set_baggage("transaction_id", "abc123")
set_baggage("priority", "high")

# When making a request, the baggage is automatically included
with telemetry.start_as_current_span("process_payment"):
    headers = {}
    telemetry.inject_context(headers)  # Adds both traceparent AND baggage headers
    # headers now contains both trace context and baggage:
    # {'traceparent': '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01',
    #  'baggage': 'user_id=42,transaction_id=abc123,priority=high'}
    response = requests.post("http://service-b/api/payment", headers=headers)

# Service B: Accessing the baggage values
from opentelemetry.baggage import get_baggage
def process_payment(request_headers):
    # Extract the propagated context (includes both trace context and baggage)
    context = telemetry.extract_context(request_headers)

    # Start a span using the extracted context
    with telemetry.start_as_current_span("verify_payment", context=context):
        # Access the baggage values
        user_id = get_baggage("user_id")  # "42"
        priority = get_baggage("priority")  # "high"

        # Use the baggage values for business logic
        if priority == "high":
            return {"status": "priority_processing"}
```

### Practical Use Cases for Baggage

1. **Customer Context**: Propagate customer IDs or session IDs across services
   without adding them to every API parameter
2. **Feature Flags**: Pass feature flag values to ensure consistent experience
   across multiple services
3. **Request Priority**: Indicate processing priority that should be respected
   by all downstream services
4. **Tenant Identification**: In multi-tenant systems, ensure all services
   process requests in the correct tenant context

Baggage is particularly useful for information that should follow the entire
transaction but isn't part of your formal API contracts.
