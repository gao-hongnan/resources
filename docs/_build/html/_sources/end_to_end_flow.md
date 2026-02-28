# OpenTelemetry End-to-End Telemetry Flow

```{contents}
:local:
:depth: 2
```

## 1. Introduction

Welcome to the observability setup for this project! This document provides a
detailed, step-by-step explanation of how we collect, process, and export
telemetry data – specifically **traces**, **metrics**, and **logs** – using
OpenTelemetry (OTel).

**Goal:** To provide a clear and rigorous understanding of the data flow,
enabling developers, even those new to OpenTelemetry, to effectively use,
maintain, and troubleshoot the observability system.

**Core Components:**

1.  **Application Code:** Instrumented using the OpenTelemetry Python SDK.
2.  **OpenTelemetry Collector:** A central agent that receives, processes, and
    exports telemetry data.
3.  **Backend Systems:** Destinations for storing and visualizing telemetry
    (e.g., Jaeger for traces, Prometheus for metrics).

We will follow the journey of telemetry data through several distinct phases,
from its generation within the application to its final storage and
visualization.

_(For a conceptual overview of OpenTelemetry and its components like the
Collector, receivers, processors, and exporters, please refer to `concept.md`)_.

## 2. High-Level Flow Diagram

This diagram illustrates the overall architecture and data path:

```{mermaid}
:zoom:

flowchart TB
    %% Main application entry point
    App[Application Code
(e.g., llm_app.py)] --> |"1. initialize_telemetry(settings)"| Init[Telemetry SDK Initialization]
    Init --> |"OTel Python SDK"| SDK["OTel SDK
(TracerProvider, MeterProvider, LoggerProvider)"]

    %% SDK generates telemetry
    SDK --> |"2. Generate: tracer.start_span()"| TraceGen["Trace Generation"]
    SDK --> |"2. Generate: meter.create_counter().add()"| MetricGen["Metric Generation"]
    SDK --> |"2. Generate: logger.info()"| LogGen["Log Generation"]

    %% SDK exports data
    subgraph SDKExport ["SDK Export Processing"]
        direction TB
        TraceGen --> SpanProc["BatchSpanProcessor"]
        MetricGen --> MetricRead["PeriodicExportingMetricReader"]
        LogGen --> LogProc["BatchLogRecordProcessor"]
        SpanProc & MetricRead & LogProc --> |"3. Batch & Format"| OTLPExport["OTLP Exporter
(gRPC/HTTP)"]
    end

    %% Collector receives data
    Collector["OpenTelemetry Collector"]
    subgraph CollectorReceivers ["Collector: Receivers"]
        direction TB
        OTLPReceiver["OTLP Receiver
(Listens on 4317/4318)"]
    end

    OTLPExport --> |"4. Send OTLP Data (Network)"| OTLPReceiver

    %% Collector processes data
    subgraph CollectorPipelines ["Collector: Processing Pipelines"]
        direction TB
        PipelineEntry["Pipeline Routing
(Traces, Metrics, Logs)"]

        subgraph TracePipeline ["Traces Pipeline"]
            direction LR
            MemLimitT[memory_limiter] --> BatchT[batch] --> ResourceT[resource]
        end
        subgraph MetricPipeline ["Metrics Pipeline"]
            direction LR
            MemLimitM[memory_limiter] --> BatchM[batch] --> ResourceM[resource]
        end
        subgraph LogPipeline ["Logs Pipeline"]
            direction LR
            MemLimitL[memory_limiter] --> BatchL[batch] --> ResourceL[resource]
        end

        OTLPReceiver --> PipelineEntry
        PipelineEntry -- "Traces" --> MemLimitT
        PipelineEntry -- "Metrics" --> MemLimitM
        PipelineEntry -- "Logs" --> MemLimitL
    end

    %% Collector exports data
    subgraph CollectorExporters ["Collector: Exporters"]
        direction TB
        JaegerExp["OTLP Exporter
(to Jaeger)"]
        PromExp["Prometheus Exporter
(Scrape Endpoint)"]
        DebugExp["Debug Exporter
(Console Output)"]
    end

    ResourceT --> |"5. Export Traces"| JaegerExp
    ResourceT --> |"5. Export Traces"| DebugExp

    ResourceM --> |"5. Export Metrics"| PromExp
    ResourceM --> |"5. Export Metrics"| DebugExp

    ResourceL --> |"5. Export Logs"| DebugExp

    %% Backends receive data
    subgraph Backends ["Observability Backends"]
        direction TB
        Jaeger["Jaeger
(Trace Storage & UI)"]
        Prometheus["Prometheus
(Metrics Storage & Querying)"]
        CollectorLogs["Collector Console Logs"]
    end

    JaegerExp --> |"6. Store Traces"| Jaeger
    PromExp --> |"6. Scrape Metrics (Pull)"| Prometheus
    DebugExp --> |"6. Display Telemetry"| CollectorLogs

    %% Style similar components
    classDef sdk fill:#cde4ff,stroke:#333,stroke-width:1px;
    classDef collector fill:#e1d5e7,stroke:#333,stroke-width:1px;
    classDef backend fill:#d5e8d4,stroke:#333,stroke-width:1px;
    classDef process fill:#f8cecc,stroke:#333,stroke-width:1px;

    class App,Init,SDK,TraceGen,MetricGen,LogGen,SDKExport,OTLPExport sdk;
    class Collector,CollectorReceivers,OTLPReceiver,CollectorPipelines,TracePipeline,MetricPipeline,LogPipeline,CollectorExporters,JaegerExp,PromExp,DebugExp collector;
    class MemLimitT,BatchT,ResourceT,MemLimitM,BatchM,ResourceM,MemLimitL,BatchL,ResourceL process;
    class Backends,Jaeger,Prometheus,CollectorLogs backend;

```

## 3. Phase 1: Telemetry Generation (Application SDK)

This phase occurs entirely within your instrumented application process (e.g.,
`llm_app.py`). The OpenTelemetry Python SDK is responsible for generating,
processing (minimally), and exporting telemetry data.

### 3.1. Initialization and Configuration

-   **Loading Configuration:** At startup, the application typically loads
    configuration from environment variables (e.g., `.env.local`) using
    libraries like `python-dotenv`. These variables define crucial OTel settings
    like the service name, version, and the target endpoint for the OTel
    Collector.
-   **Settings Management:** A Pydantic `BaseSettings` class (e.g.,
    `TelemetrySettings` in `instrumentation.settings`) parses and validates
    these environment variables, providing a structured, typed configuration
    object (`settings`). This ensures configuration is explicit and correct.
-   **Telemetry Facade & SDK Setup:** The `Telemetry.from_settings(settings)`
    class method acts as a factory and central point of interaction. It performs
    the core SDK initialization:
    -   **Resource Creation:** Creates an OTel `Resource` object, bundling
        attributes like `service.name`, `service.version`,
        `deployment.environment` defined in the settings. This `Resource` is
        associated with all telemetry emitted by this SDK instance.
    -   **Provider Setup:** Initializes the global `TracerProvider`,
        `MeterProvider`, and `LoggerProvider`. These are the entry points for
        creating Tracers, Meters, and Loggers.
    -   **Processors:** Configures processors for each signal type. Crucially,
        this includes:
        -   `BatchSpanProcessor`: Buffers completed spans and exports them in
            batches.
        -   `BatchLogRecordProcessor`: Buffers log records and exports them in
            batches.
    -   **Exporters:** Configures exporters based on settings. Typically,
        `OTLPSpanExporter`, `OTLPMetricExporter`, and `OTLPLogExporter` are set
        up, pointing to the Collector's OTLP endpoint (e.g.,
        `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`). The protocol
        (gRPC/HTTP) must match the Collector's receiver configuration.
    -   **Metric Reader:** Configures a `PeriodicExportingMetricReader` which
        links the `MeterProvider` to the `OTLPMetricExporter`, collecting and
        exporting metrics at a regular interval (e.g., every 30 seconds).
    -   **Logging Integration:** Configures Python's standard `logging` module
        to use an OTel `LoggingHandler`, ensuring logs are captured by the OTel
        `LoggerProvider` and automatically correlated with active traces.
-   **Singleton Pattern:** The `Telemetry` class often implements a thread-safe
    singleton pattern (using `lru_cache` or a custom mechanism) to ensure only
    one instance of the SDK is configured and used throughout the application.
-   **Custom Metric Instruments:** The application uses the initialized
    `telemetry` facade to create specific metric instruments needed for its
    domain (e.g., `telemetry.create_counter("llm.requests.total", ...)`,
    `telemetry.create_histogram("llm.request.duration", ...)`). These
    instruments are now ready to record measurements.

### 3.2. Runtime Instrumentation APIs

During application execution (e.g., handling an HTTP request), the SDK APIs are
used to generate telemetry:

-   **Traces (`telemetry.tracer`):**
    -   **Span Creation:**
        `telemetry.start_as_current_span("operation_name", ...)` is the primary
        method. It starts a new `Span`, makes it active in the current execution
        context, and returns a context manager (for use with `with`). When the
        `with` block exits, the span is automatically ended.
    -   **Automatic Instrumentation:** If auto-instrumentation libraries (e.g.,
        `opentelemetry-instrumentation-fastapi`,
        `opentelemetry-instrumentation-httpx`) are active, they automatically
        create spans for supported operations (incoming requests, outgoing HTTP
        calls, DB queries) without manual code.
    -   **Span Attributes & Events:** Inside a span's context, you can add
        attributes (`span.set_attribute("key", "value")`), record events
        (`span.add_event("message")`), and record exceptions
        (`span.record_exception(exc)`). The span's status (OK/Error) is
        typically set automatically based on whether an exception occurred.
-   **Metrics (`telemetry.meter`):**
    -   **Recording Measurements:** The previously created instruments are used
        to record values:
        -   `counter.add(1, {"attr": "value"})`
        -   `histogram.record(duration, {"attr": "value"})`
        -   `up_down_counter.add(1 / -1, {"attr": "value"})`
        -   `gauge.set(value, {"attr": "value"})` (via observable callbacks)
    -   Attributes (key-value pairs) provide dimensions for filtering and
        aggregation in the backend.
-   **Logs (`telemetry.log` or standard `logging`):**
    -   Using the facade
        `telemetry.log(level=logging.INFO, message="...", extra_attributes={})`
        or standard `logging.info("...")` calls generates log records.
    -   The OTel logging handler automatically captures these, attaches the
        current `TraceId`, `SpanId`, and `Resource` attributes, and forwards
        them to the configured `LogRecordProcessor`.

### 3.3. Context Propagation

A key aspect of distributed tracing is maintaining causality across process
boundaries (e.g., one service calling another).

-   **Injection:** When making an outgoing request (e.g., an HTTP call via
    `httpx`), the application uses `telemetry.inject_context(carrier)` (where
    `carrier` is often a dictionary for HTTP headers). The SDK injects the
    current active trace context (Trace ID, Span ID, trace flags, trace state)
    into the carrier using a standard format (usually W3C Trace Context
    `traceparent` and `tracestate` headers).
-   **Extraction:** On the receiving side (e.g., in middleware like
    `TraceContextMiddleware`), the application uses
    `telemetry.extract_context(carrier)` to retrieve trace context from the
    incoming request headers.
-   **Continuity:** If context is successfully extracted, new spans created by
    the receiving service become children of the span from the calling service,
    preserving the distributed trace chain. If no context is found, a new trace
    is started.

### 3.4. SDK Internal Processing and Export

-   **Batching:** As described in Initialization, the `BatchSpanProcessor` and
    `BatchLogRecordProcessor` collect completed spans and log records. They
    buffer these items in memory until either a configured time interval elapses
    (e.g., 5 seconds) or a maximum batch size is reached (e.g., 512 items).
-   **Metric Aggregation:** The `PeriodicExportingMetricReader` wakes up at its
    configured interval (e.g., 30s), collects the latest aggregated values from
    all metric instruments (e.g., sum for counters, histogram buckets), and
    resets state where necessary (for delta temporality).
-   **Serialization & Export:** When a batch is ready (for spans/logs) or the
    metric collection interval triggers, the corresponding OTLP exporter:
    1.  Serializes the batch of telemetry items into the OTLP Protobuf format.
    2.  Establishes a network connection (gRPC or HTTP) to the configured OTel
        Collector endpoint (`OTEL_EXPORTER_OTLP_ENDPOINT`).
    3.  Sends the serialized OTLP message over the network.
    4.  Handles potential connection errors or backpressure signals from the
        Collector (exporters often have basic retry mechanisms).

This marks the end of the application's direct involvement for that batch of
telemetry. The responsibility shifts to the OTel Collector.

## 4. Phase 2: Data Reception & Processing (OTel Collector)

The OTel Collector acts as a dedicated, standalone service optimized for
handling telemetry data efficiently and reliably.

### 4.1. OTLP Receiver

-   **Listening:** The Collector is configured with an `otlp` receiver in
    `collector-config.yaml`. This receiver binds to specific network interfaces
    and ports (e.g., `0.0.0.0:4317` for gRPC, `0.0.0.0:4318` for HTTP) and
    listens for incoming connections from application SDKs.
-   **Protocol Handling:** It accepts connections using the specified protocols
    (gRPC and/or HTTP).
-   **Deserialization:** Upon receiving an OTLP message, the receiver parses the
    Protobuf payload.
-   **Identification & Routing:** It identifies the signal type (traces,
    metrics, logs) based on the OTLP message structure and converts the data
    into the Collector's internal data model. It then routes this internal data
    to the beginning of the appropriate pipeline(s) defined in the
    `service.pipelines` section of the configuration.

### 4.2. Pipeline Processing

Data flows sequentially through the processors configured for its specific
pipeline (e.g., `service.pipelines.traces.processors`). The order of processors
matters. A typical robust pipeline includes:

1.  **`memory_limiter` Processor:**
    -   **Purpose:** Acts as a crucial safety mechanism to prevent the Collector
        from crashing due to excessive memory usage, especially under high load
        or if downstream exporters are slow/unavailable.
    -   **Mechanism:** Monitors the Collector's memory footprint. If usage
        exceeds a configured `limit_mib`, it starts rejecting new data
        (`ballast_size_mib` can influence Go GC behavior). If usage hits a
        `spike_limit_mib`, it triggers garbage collection more aggressively and
        continues rejecting data. This rejection signals backpressure to the
        receiver, which ideally propagates to the SDK (causing retries or data
        dropping at the source).
    -   **Placement:** Typically placed **first** in the pipeline to check
        memory before any significant processing occurs.
2.  **`batch` Processor:**
    -   **Purpose:** Improves export efficiency and reduces load on backend
        systems by grouping telemetry items received by the Collector into
        larger batches.
    -   **Mechanism:** Similar to the SDK batch processors, it collects items
        based on time (`timeout`) or count (`send_batch_size`) before flushing
        the batch to the next processor or exporter. This amortizes the overhead
        of export calls.
    -   **Placement:** Often placed after the `memory_limiter`.
3.  **`resource` Processor:**
    -   **Purpose:** Ensures consistent metadata by adding, modifying, or
        removing resource attributes attached to telemetry data.
    -   **Mechanism:** Configured with actions (`upsert`, `insert`, `update`,
        `delete`) for specific attributes (e.g., ensuring `service.name` or
        `deployment.environment` is present and correct, potentially adding k8s
        attributes like `k8s.pod.name`).
    -   **Placement:** Often placed after batching, before exporting, to ensure
        all data sent to backends has the desired, consistent resource
        information.

_(Other processors like `attributes`, `span`, `filter`, `probabilistic_sampler`
can be added for more advanced filtering, modification, or sampling
requirements.)_

## 5. Phase 3: Data Exporting (Collector to Backends)

After passing through all processors in its pipeline, the (now processed and
batched) telemetry data reaches the exporter(s) configured for that pipeline
(`service.pipelines.<signal>.exporters`).

-   **Fan-Out:** A single pipeline can have multiple exporters. The Collector
    fans out the data, sending a copy to each configured exporter for that
    signal type.

### 5.1. Trace Exporters

-   **`otlp` Exporter (to Jaeger):**
    -   **Mechanism:** Configured with the OTLP endpoint of the Jaeger collector
        (e.g., `endpoint: jaeger:4317`). It serializes trace batches into OTLP
        and **pushes** them via gRPC (usually) to Jaeger. Modern Jaeger versions
        natively support OTLP ingestion.
    -   **Reliability:** Includes built-in retry logic with exponential backoff
        to handle temporary network issues or Jaeger unavailability.
-   **`debug` Exporter:**
    -   **Mechanism:** Logs the received trace data (spans) to the Collector's
        standard output/error stream. Verbosity can be configured (`detailed`).
    -   **Purpose:** Primarily for debugging and verifying data flow during
        development or troubleshooting. It confirms that traces reached the
        Collector and passed through the pipeline, even if the primary backend
        exporter fails.

### 5.2. Metric Exporters

-   **`prometheus` Exporter:**
    -   **Mechanism:** Does **not** push data. Instead, it acts as a **pull**
        endpoint. It maintains the current state of received metrics internally
        and exposes an HTTP endpoint (e.g., `endpoint: 0.0.0.0:8889`). A
        separate Prometheus server must be configured to periodically scrape
        (`/metrics`) this endpoint. On scrape, the exporter formats the current
        metrics into the Prometheus text exposition format and returns them in
        the HTTP response.
    -   **Configuration:** Options like `namespace`, `send_timestamps`, and
        `resource_to_telemetry_conversion` control the formatting and labeling
        of exposed metrics.
-   **`debug` Exporter:**
    -   **Mechanism:** Logs the received metric data points to the Collector's
        console. Useful for verifying that metrics are arriving and being
        processed correctly.

### 5.3. Log Exporters

-   **`debug` Exporter:**
    -   **Mechanism:** In the provided example configuration, this is often the
        only exporter for logs. It prints the log records (including attributes
        and trace context) to the Collector's console.
    -   **(Alternative):** In a production setup, you would typically add other
        exporters here, such as `loki`, `otlp` (to a log-compatible OTLP backend
        like Grafana Loki with its OTLP receiver), or `file` to send logs to
        persistent storage and analysis systems.

## 6. Phase 4: Backend Storage & Visualization

The final destinations where telemetry data is stored, analyzed, and visualized.

-   **Jaeger:** Receives OTLP trace data from the Collector. Stores spans
    (in-memory for development, or backend databases like
    Elasticsearch/Cassandra for production). Provides a UI (e.g., port 16686)
    for searching, visualizing distributed traces, analyzing latency, and
    understanding service dependencies.
-   **Prometheus:** Periodically scrapes the Collector's Prometheus exporter
    endpoint. Stores the received metrics in its time-series database. Provides
    a UI (e.g., port 9090) for querying metrics using PromQL and basic graphing.
    Often used as a data source for Grafana for richer dashboards.
-   **Collector Logs (via Debug Exporter):** Telemetry logged by the `debug`
    exporter is visible in the standard output/logs of the `otel-collector`
    service (e.g., via `docker logs otel-collector`). This is not persistent
    storage but useful for immediate feedback during development.

## 7. Phase 5: Reliability, Monitoring & Extensions

Several features contribute to the robustness and maintainability of this setup:

-   **Batching (SDK & Collector):** Reduces network overhead, improves
    throughput, allows buffering during transient backend issues.
-   **Memory Limiter (Collector):** Prevents Collector OOM crashes under heavy
    load through controlled data dropping and backpressure.
-   **Exporter Retries:** OTLP exporters automatically retry sending data on
    transient failures, preventing data loss.
-   **Backpressure:** The system (ideally) propagates backpressure from
    overloaded components (Collector memory limiter, exporter queues) back to
    the source (SDK), potentially causing the SDK to slow down or drop data
    gracefully.
-   **Collector Extensions:**
    -   **`health_check`:** Exposes an HTTP endpoint (e.g., port 13133) for
        external monitoring systems (like Kubernetes liveness/readiness probes)
        to verify the Collector process is running and responsive. Essential for
        automated operations.
    -   **`pprof`:** Enables Go's built-in performance profiling endpoint (e.g.,
        port 1777). Allows developers to diagnose CPU and memory usage
        bottlenecks within the Collector itself.
    -   **`zpages`:** Provides web-based diagnostic pages (e.g., port 55679)
        showing internal Collector state, including pipeline statistics, trace
        information, and configuration details. Useful for live debugging.

## 8. Detailed Walkthrough: Tracing a Request

Let's trace a hypothetical request to the `/chat` endpoint in `llm_app.py`
through the system:

1.  **Request In (App):** A POST request hits `/chat`.
2.  **Middleware Span (App):** `TraceContextMiddleware` extracts any incoming
    `traceparent` header (or starts a new trace). It uses
    `telemetry.start_as_current_span("POST /chat")` to create `Span 1 (SERVER)`.
3.  **Route Handler Span (App):** Inside the `/chat` function,
    `telemetry.start_as_current_span("chat_operation")` creates
    `Span 2 (INTERNAL)`, a child of Span 1.
4.  **Metric Recording (App):** A counter like `chat_requests_total.add(1)`
    might be called.
5.  **Logging (App):** `telemetry.log(logging.INFO, "Processing chat request")`
    creates a log record, automatically associating it with Span 2.
6.  **Internal Call Span (App):** The code calls `simulate_llm_api_call()`.
    Inside this function, `telemetry.start_as_current_span("llm.simulate_call")`
    creates `Span 3 (CLIENT or INTERNAL)`, a child of Span 2. Metrics related to
    the simulation (duration, tokens) are recorded within this span's context.
7.  **Span Completion (App):** As `with` blocks exit and functions return, Spans
    3, 2, and 1 are ended sequentially. Their durations are calculated, statuses
    set, and any exceptions recorded.
8.  **SDK Batching & Export (App):** The completed spans (1, 2, 3), the log
    record, and collected metrics are processed by their respective SDK
    batchers/readers. Eventually, OTLP exporters send batches containing this
    telemetry to the Collector (e.g., `otel-collector:4317`).
9.  **Collector Reception:** The Collector's `otlp` receiver gets the OTLP
    messages.
10. **Collector Processing:** The spans, metrics, and logs are routed to their
    pipelines. They pass through `memory_limiter`, `batch`, and `resource`
    processors.
11. **Collector Export (Traces):** The trace batch (containing Spans 1, 2, 3) is
    sent to the `otlp` (to Jaeger) exporter AND the `debug` exporter.
12. **Collector Export (Metrics):** The metric batch is processed by the
    `prometheus` exporter (updating its internal state) AND the `debug`
    exporter.
13. **Collector Export (Logs):** The log batch is sent to the `debug` exporter.
14. **Backend Storage (Jaeger):** The `otlp` exporter successfully sends the
    trace batch to Jaeger, which stores the spans.
15. **Backend Storage (Prometheus):** The next time Prometheus scrapes the
    Collector's `/metrics` endpoint, it retrieves the latest metric values,
    including the incremented `chat_requests_total`.
16. **Backend Storage (Logs):** The log record appears in the `otel-collector`
    container's console output.
17. **Visualization:** A developer can now query Jaeger to find the trace for
    the `/chat` request, view the relationship between Spans 1, 2, and 3, see
    their durations and attributes, and find the correlated log message. They
    can query Prometheus/Grafana to see the `chat_requests_total` metric over
    time.

This detailed flow illustrates how telemetry provides end-to-end visibility,
correlating different signals (traces, metrics, logs) across the application and
infrastructure components.

## 9. Best Practices & Troubleshooting

_(This section summarizes key points from `concept.md`'s "Best Practices"
section for quick reference)_

-   **Configuration Alignment:** Ensure `OTEL_EXPORTER_OTLP_ENDPOINT` and
    `OTEL_EXPORTER_OTLP_PROTOCOL` in the application SDK match the Collector's
    `otlp` receiver settings (ports 4317/gRPC vs 4318/HTTP). Mismatches are a
    common cause of "no data".
-   **Service Name:** Always set the `service.name` resource attribute (via SDK
    config `OTEL_SERVICE_NAME` or Collector `resource` processor) for meaningful
    grouping in backends.
-   **Collector Processors:** Use `batch` and `memory_limiter` in production
    Collector pipelines for performance and stability.
-   **Prometheus Scrapes:** Remember Prometheus _pulls_ data. Ensure the
    Prometheus server is configured to scrape the Collector's `prometheus`
    exporter endpoint, and that the endpoint is network-accessible.
-   **Debug Exporter:** Use the `debug` exporter in the Collector during
    development/troubleshooting to verify data arrival and format _before_ it
    reaches backends.
-   **Check Logs:** Examine both application logs and Collector logs for errors
    (connection issues, configuration problems).
-   **Collector Extensions:** Leverage `health_check` for monitoring, and
    `pprof`/`zpages` for advanced Collector debugging/profiling.
-   **Jaeger OTLP:** Ensure the target Jaeger instance has OTLP ingestion
    enabled (`COLLECTOR_OTLP_ENABLED=true` for Jaeger all-in-one).

By understanding this flow and adhering to best practices, you can effectively
leverage OpenTelemetry for robust observability in this project.
