# Concept

```{contents}
:local:
```

## Motivation

### The Problem: Understanding Complex Systems

Modern software, especially web services, often consists of many interconnected
parts (microservices, databases, external APIs). When something goes wrong (like
a slow request or an error), figuring out _where_ and _why_ can be incredibly
difficult. It's like trying to find a single faulty wire in a huge, tangled
mess.

### The Solution: Observability with OpenTelemetry

**Observability** is about designing your systems so you can understand their
internal state just by observing their external outputs. Think of it like a
car's dashboard – it gives you speed (metric), engine temperature (metric), and
maybe a check engine light (log/event) without you needing to open the hood.

To achieve observability, we collect **telemetry data**:

1.  **Traces:** Record the path of a single request as it travels through
    different services. Helps answer "Where did this request go?" and "Where did
    it spend its time?".
2.  **Metrics:** Numerical measurements over time (e.g., number of requests per
    second, CPU usage, error rate). Helps answer "How is the system performing
    overall?" and "Are resource limits being hit?".
3.  **Logs:** Timestamped text records of specific events (e.g., an error
    occurred, user logged in, configuration loaded). Helps answer "What specific
    event happened at this time?".

**OpenTelemetry (OTel)** is an open-source industry standard and collection of
tools, APIs (Application Programming Interfaces), and SDKs (Software Development
Kits) for generating, collecting, and exporting this telemetry data. It provides
a vendor-neutral way to instrument your code, meaning you aren't locked into a
specific monitoring tool provider. Your applications use these OTel libraries to
generate the traces, metrics, and logs described above.

### Managing Telemetry Data with the OTel Collector

Now that your applications are generating this valuable telemetry data, how do
you get it efficiently and reliably to the systems where you'll analyze and
visualize it? Sending data directly from every application instance to
potentially multiple backend systems (like a logging platform, a metrics
database, _and_ a tracing system) can become complex and inefficient.

This is where the
[**OpenTelemetry Collector**](https://opentelemetry.io/docs/collector/) becomes
essential. The Collector is a standalone application designed specifically to
receive, process, and export telemetry data. It acts as a flexible and robust
agent or gateway in your observability pipeline. Think of it like a highly
configurable mail sorting facility for your observability signals:

-   **Receives:** It listens for incoming telemetry data from various sources,
    primarily your instrumented applications using protocols like
    `OTLP (OpenTelemetry Protocol)`, but potentially other formats as well.
-   **Processes:** Before forwarding the data, the Collector can perform various
    processing tasks. This might include filtering out sensitive information,
    adding common attributes (like deployment environment), modifying data
    (e.g., renaming metrics), sampling traces to reduce volume, or batching data
    for more efficient export.
-   **Exports:** Finally, it sends the processed data to one or more configured
    backend systems. These could be open-source tools like `Prometheus`,
    `Jaeger`, or `Loki`, or commercial observability platforms.

Using a Collector centralizes the logic for handling telemetry data. Your
applications only need to be configured to send data to the Collector's address.
The Collector then takes on the responsibility of aggregation, transformation,
and routing to the final destinations. This decoupling makes your architecture
more resilient and easier to manage, especially as your systems or backend
choices evolve. The specific configuration defining how the collector receives,
processes, and exports data is managed through a configuration file, such as the
[`collector-config.yaml`](../config/collector-config.yaml) file mentioned.

## Basic Networking Concepts for Services and Containers

### Networking 101

Understanding how services talk to each other over a network is crucial,
especially when working with tools like OpenTelemetry and Docker Compose. Let's
break down some key terms:

-   **Host:** This is simply the computer or server where a program is running.
    It could be your physical laptop, a virtual machine (VM) in the cloud, or
    even a container (like those managed by Docker). Think of it as the
    "machine".

-   **Port:** Imagine a large building (the host machine) with many numbered
    doors (ports). When programs need to communicate over a network, they
    connect to a specific "door" or port number on the target host. This allows
    multiple services to run on the same host without interfering with each
    other.

    -   Ports are numbered from 0 to 65535.
    -   Many common services have default ports (e.g., web servers often use
        port 80 for HTTP and 443 for HTTPS).
    -   OpenTelemetry's OTLP protocol, for example, often uses port `4317` (for
        gRPC) and `4318` (for HTTP).

-   **Listening on a Port:** When a service (like an OTel Collector receiver) is
    "listening" on a specific port, it means it's actively waiting at that
    numbered door on its host, ready to accept incoming network connections or
    data sent specifically to that port number.

-   **IP Address:** This is like the unique street address for a host machine on
    a network. It allows other machines to find it and send data to it. There
    are a few special IP addresses:

    -   **`127.0.0.1` (`localhost`):** This special IP address always means
        "this machine itself". When a service listens on `127.0.0.1`, it can
        only accept connections originating from the _same_ machine. The
        hostname `localhost` usually resolves to this IP address. It's often
        used for local development or services that should only talk to
        themselves.
    -   **`0.0.0.0`:** This special address isn't a real destination but is used
        when configuring a service to listen. It means "listen on _all_
        available network interfaces on this host". If a host has multiple ways
        to be reached (e.g., Wi-Fi with IP `192.168.1.5`, Ethernet with IP
        `10.0.0.2`, and the `localhost` interface `127.0.0.1`), a service
        listening on `0.0.0.0` will accept connections coming into _any_ of
        those addresses on the specified port. This is very common for services
        (like web servers or the OTel Collector) that need to be reachable from
        other machines or containers.

-   **Endpoint (`<HOST>:<PORT>`):** This combination of a host identifier (an IP
    address like `0.0.0.0` or `192.168.1.5`, or a hostname like `localhost` or
    `otel-collector`) and a port number (`4317`) defines a specific
    communication endpoint.
    -   A _server_ or _receiver_ (like the OTel Collector) listens on an
        endpoint (e.g., `0.0.0.0:4317` means listen on port 4317 on all
        interfaces).
    -   A _client_ (like your application sending telemetry) needs to know the
        target endpoint to connect to (e.g., `192.168.1.10:4317` or
        `otel-collector:4317`).

### Networking in Containers (Docker / Docker Compose)

When using containers, things work slightly differently, making the following
concepts important:

-   **Container Network Isolation:** By default, Docker creates a private
    network for containers launched together (e.g., via Docker Compose). Each
    container gets its own internal IP address within this private network.
    Services running inside a container are initially only reachable by other
    containers on the same Docker network, not directly from your host machine.
    `localhost` or `127.0.0.1` _inside_ a container refers to the container
    _itself_, not your host machine.

-   **Port Mapping:** To access a service running _inside_ a container from
    _outside_ (e.g., from your host machine's browser or another application not
    in the same Docker network), you need to map a port from the host machine to
    the container port.

    -   In Docker Compose (`docker-compose.yaml`), this is done using the
        `ports:` section.
    -   Syntax is typically `HOST_PORT:CONTAINER_PORT` (often written as a
        string like `"4317:4317"`).
    -   Example: `ports: ["8080:80"]` means traffic sent to port `8080` on your
        _host machine_ will be forwarded to port `80` _inside_ the container. If
        the OTel Collector inside a container listens on `0.0.0.0:4317`, you
        might use `ports: ["4317:4317"]` to make it reachable via
        `localhost:4317` (or `<your_host_ip>:4317`) on your host machine.

-   **Service Discovery (Service Names):** How do containers within the same
    Docker Compose setup find each other? Docker's networking allows containers
    on the same network to find each other using the _service names_ defined in
    your `docker-compose.yaml` file.
    -   If you define a service named `otel-collector` and another named
        `my-app` in your `docker-compose.yaml`, the `my-app` container can
        typically send data to the collector using the hostname `otel-collector`
        and the port the collector is listening on internally.
    -   Example: Your application code inside the `my-app` container might
        configure its OTel exporter to send data to the endpoint
        `otel-collector:4317`. Docker automatically resolves `otel-collector` to
        the correct internal IP address of the collector container within the
        Docker network.

Understanding these concepts helps demystify how services, especially within
containers, are configured to listen for traffic (`0.0.0.0:<port>`), how they
are made accessible from the outside (`ports:` mapping), and how they
communicate with each other (`<service-name>:<port>`).

## Anatomy of Telemetry Flow

Let's first see the flow of telemetry data from the application to the
collector. It is key to understand the flow of telemetry data to understand the
configuration of the collector.

In short, the flow is as follows:

1.  The application code uses the OpenTelemetry SDK to generate telemetry data.
2.  The SDK generates telemetry data and sends it to the collector via the OTLP
    protocol.
3.  The collector receives the telemetry data and processes it.
4.  The collector exports the telemetry data to the backend systems.

> This allows for a separation of concerns, as you can change the backend
> systems by reconfiguring the collector without changing the application code.

```{mermaid}
:zoom:

flowchart TB
    %% Application and SDK Layer (From Diagram 1)
    subgraph "Application Layer"
        App["Application Code"]
        TelemFacade["Telemetry Facade"]

        subgraph "OpenTelemetry SDK"
            direction TB
            TracerProvider["TracerProvider"]
            MeterProvider["MeterProvider"]
            LoggerProvider["LoggerProvider"]
        end

        subgraph "SDK Processors/Readers"
             direction TB
            BatchSpanProcessor["BatchSpanProcessor"]
            PeriodicMetricReader["PeriodicMetricReader"]
            BatchLogProcessor["BatchLogProcessor"]
        end

        subgraph "SDK Exporters"
             direction TB
            OTLPTraceExporter["OTLPSpanExporter"]
            OTLPMetricExporter["OTLPMetricExporter"]
            OTLPLogExporter["OTLPLogExporter"]
        end
    end

    %% OTLP Protocol Layer (From Diagram 1)
    subgraph "Protocol Layer"
        direction LR
        OTLP["OTLP/gRPC (4317)"]
        OTLPHTTP["OTLP/HTTP (4318)"]
    end


    %% Collector Layer (Combining Both Diagrams)
    subgraph "OpenTelemetry Collector"
        direction TB

        subgraph "Collector: Extensions"
            direction TB
            HealthCheck["Health Check (13133)"]
            PProf["PProf Profiling (1777)"]
            ZPages["ZPages Diagnostics (55679)"]
            %% Note: Extensions exist alongside, not directly in data path typically
        end

        subgraph "Collector: Receivers"
            direction TB
            OTLPReceiver["OTLP Receiver (gRPC/HTTP)"]
        end

        %% Explicit Pipeline Processing (Inspired by Diagram 2)
        subgraph "Collector: Pipeline Processing"
            direction TB

            subgraph "Traces Pipeline Processors"
                direction LR
                style TraceProcess fill:#fff,stroke:#6f42c1,stroke-dasharray: 5 5
                BatchProcessorT["Batch Processor"] --> MemoryLimiterT["Memory Limiter"] --> SamplingProcessorT["Sampling Processor"]
            end

            subgraph "Metrics Pipeline Processors"
                direction LR
                 style MetricsProcess fill:#fff,stroke:#6f42c1,stroke-dasharray: 5 5
                %% Assuming simpler pipeline for metrics based on common configs
                BatchProcessorM["Batch Processor"] --> MemoryLimiterM["Memory Limiter"]
            end

             subgraph "Logs Pipeline Processors"
                direction LR
                 style LogsProcess fill:#fff,stroke:#6f42c1,stroke-dasharray: 5 5
                 %% Assuming simpler pipeline for logs
                BatchProcessorL["Batch Processor"] --> MemoryLimiterL["Memory Limiter"]
            end
        end


        subgraph "Collector: Exporters"
            direction TB
            DebugExporter["Debug Exporter"]
            PromExporter["Prometheus Exporter (8889)"]
            OTLPJaegerExporter["OTLP Exporter (to Jaeger)"]
        end

    end

    %% Backend Systems Layer (From Diagram 1)
    subgraph "Observability Backends"
        direction LR
        Prometheus["Prometheus"]
        Jaeger["Jaeger"]
        Loki["Loki (Future)"]
        Alerting["Alerting Systems"]
    end

    %% Connections: App SDK Internal
    App --> TelemFacade
    TelemFacade --> TracerProvider
    TelemFacade --> MeterProvider
    TelemFacade --> LoggerProvider

    TracerProvider --> BatchSpanProcessor
    MeterProvider --> PeriodicMetricReader
    LoggerProvider --> BatchLogProcessor

    BatchSpanProcessor --> OTLPTraceExporter
    PeriodicMetricReader --> OTLPMetricExporter
    BatchLogProcessor --> OTLPLogExporter

    %% Connections: SDK to Protocol
    OTLPTraceExporter --> OTLP
    OTLPMetricExporter --> OTLP
    OTLPLogExporter --> OTLP

    OTLPTraceExporter -.-> OTLPHTTP
    OTLPMetricExporter -.-> OTLPHTTP
    OTLPLogExporter -.-> OTLPHTTP

    %% Connections: Protocol to Collector Receiver
    OTLP --> OTLPReceiver
    OTLPHTTP --> OTLPReceiver

    %% Connections: Receiver to Pipelines (Connect to START of each pipeline processing)
    OTLPReceiver -- "Traces" --> BatchProcessorT
    OTLPReceiver -- "Metrics" --> BatchProcessorM
    OTLPReceiver -- "Logs" --> BatchProcessorL

    %% Connections: Pipeline Processors to Exporters (Connect from END of each pipeline processing)
    SamplingProcessorT -- "Trace Data" --> OTLPJaegerExporter
    SamplingProcessorT -- "Trace Data" --> DebugExporter

    MemoryLimiterM -- "Metric Data" --> PromExporter
    MemoryLimiterM -- "Metric Data" --> DebugExporter

    MemoryLimiterL -- "Log Data" --> DebugExporter
    %% Assuming DebugExporter can handle all signal types

    %% Connections: Collector Exporters to Backends
    PromExporter -- "HTTP Scrape (Pull)" --> Prometheus
    OTLPJaegerExporter -- "OTLP/gRPC (Push)" --> Jaeger
    %% DebugExporter connection to Loki is conceptual/placeholder
    DebugExporter -.-> Loki


    %% Connections: Backends to Alerting
    Prometheus --> Alerting

    %% Styling (From Diagram 1, applied to relevant nodes)
    classDef application fill:#f8d7da,stroke:#dc3545,stroke-width:2px
    classDef sdk fill:#d1e7dd,stroke:#198754,stroke-width:2px
    classDef sdkProcessor fill:#fff3cd,stroke:#ffc107,stroke-width:2px
    classDef sdkExporter fill:#cff4fc,stroke:#0dcaf0,stroke-width:2px
    classDef protocol fill:#e2e3e5,stroke:#6c757d,stroke-width:2px

    classDef collectorReceiver fill:#d0bfff,stroke:#6f42c1,stroke-width:2px
    %% Use distinct IDs for processors if they represent different configurations
    classDef collectorProcessor fill:#ffc107,stroke:#fd7e14,stroke-width:2px
    classDef collectorExporter fill:#20c997,stroke:#198754,stroke-width:2px
    classDef collectorExtension fill:#f8f9fa,stroke:#212529,stroke-width:2px

    classDef backend fill:#adb5bd,stroke:#495057,stroke-width:2px

    %% Apply styles
    class App,TelemFacade application
    class TracerProvider,MeterProvider,LoggerProvider sdk
    class BatchSpanProcessor,PeriodicMetricReader,BatchLogProcessor sdkProcessor
    class OTLPTraceExporter,OTLPMetricExporter,OTLPLogExporter sdkExporter
    class OTLP,OTLPHTTP protocol

    class OTLPReceiver collectorReceiver
    class BatchProcessorT,MemoryLimiterT,SamplingProcessorT,BatchProcessorM,MemoryLimiterM,BatchProcessorL,MemoryLimiterL collectorProcessor
    class PromExporter,OTLPJaegerExporter,DebugExporter collectorExporter
    class HealthCheck,PProf,ZPages collectorExtension

    class Prometheus,Jaeger,Loki,Alerting backend
```

At a very high level, we see a pseudo example:

In our code, we might have:

```python
# Application code exporter - sends TO the collector
otlp_exporter = OTLPSpanExporter(
    endpoint="http://otel-collector:4317"  # Collector address
)
provider = TracerProvider()
processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(processor)
```

This corresponds to first pointer above "Your application code uses the SDK with
an OTLP exporter to send telemetry to the collector".

Following this, we see that in our
[`collector-config.yaml`](../config/collector-config.yaml) file, the `receivers`
section is configured to receive OTLP data on port 4317 (and 4318 for HTTP). And
indeed our code has endpoints that point to this address:

```python
otlp_exporter = OTLPSpanExporter(
    endpoint="http://otel-collector:4317"  # Collector address
)
```

This means that when we run our application, it will send telemetry data to the
collector at `http://otel-collector:4317`. This corresponds to the 2nd pointer
above "The collector receives this data via its OTLP receiver".

Next, the 3rd pointer above "The collector processes the data (batching,
filtering, enriching)" will then process this data via batching etc.

Lastly, the 4th pointer above "The collector's exporters forward the data to
various backends" will then send the data to a Jaeger backend and a Prometheus
backend."

And in our [`collector-config.yaml`](../config/collector-config.yaml) file, we
might have:

```yaml
# Collector exporters - send FROM the collector to backends
exporters:
    otlp:
        endpoint: jaeger:4317 # Jaeger backend
    prometheus:
        endpoint: 0.0.0.0:8889 # For Prometheus to scrape
```

### 1. Generation Phase: Application-Level Telemetry Instantiation

-   **Instrumentation Context:** Telemetry generation is initiated within the
    instrumented `Application Code`. This occurs either through manual
    instrumentation (explicit API calls to OTel SDK) or automatic
    instrumentation (libraries that intercept standard operations like HTTP
    requests or DB calls). Central to this is **Context Propagation**, where
    metadata (like Trace IDs and Span IDs) is carried across asynchronous
    boundaries and process hops, ensuring causal links are maintained.
-   **SDK Core Components:**
    -   **Providers (`TracerProvider`, `MeterProvider`, `LoggerProvider`):**
        These act as factories and registries for their respective signal types.
        They manage the SDK's configuration (e.g., Resource attributes, Sampler
        for traces, Views for metrics) and provide access to `Tracer`, `Meter`,
        and `Logger` instances.
    -   **API Interfaces (`Tracer`, `Meter`, `Logger`):** These are the
        interfaces used by instrumentation code. For example,
        `Tracer.start_span()` initiates a trace span, `Meter.create_counter()`
        defines a metric instrument, and `Logger.emit()` captures a log record.
    -   **Signal Processors/Readers:**
        -   **`SpanProcessor` (`BatchSpanProcessor`, `SimpleSpanProcessor`):**
            Invoked on span lifecycle events (typically `on_start`, `on_end`).
            The `BatchSpanProcessor` accumulates completed spans in a queue and
            flushes them periodically or when the queue reaches a certain size
            to an associated `SpanExporter`. The `SimpleSpanProcessor` exports
            spans immediately upon completion (primarily for debugging).
        -   **`MetricReader` (`PeriodicMetricReader`):** Responsible for
            collecting aggregated metric data from all registered instruments at
            defined intervals. It pulls delta or cumulative values (depending on
            configuration and instrument type) and passes them to an associated
            `MetricExporter`.
        -   **`LogRecordProcessor` (`BatchLogRecordProcessor`):** Similar to the
            span processor, it batches log records before exporting them via a
            `LogRecordExporter`.
-   **Data Instantiation Example:** When an incoming HTTP request hits an
    instrumented server:
    1.  Auto-instrumentation (or manual code) extracts any incoming trace
        context (Trace ID, Parent Span ID) via context propagation.
    2.  `Tracer.start_span()` creates a new `Span` object, marking the start
        time, associating it with the extracted or a new Trace ID, and setting
        attributes (HTTP method, URL, etc.). This span becomes the "current"
        span in the execution context.
    3.  A `Counter` metric instrument (obtained via `Meter.create_counter()`)
        might be incremented (`counter.add(1)`). The SDK internally aggregates
        this increment.
    4.  A `LogRecord` might be emitted via the `LoggerProvider`'s logger,
        capturing timestamp, severity, body, and attributes. The current
        Trace/Span ID is automatically associated if configured.
    5.  As the request completes, `span.end()` is called, recording the end time
        and status. The `SpanProcessor`'s `on_end` method is triggered,
        potentially adding the completed span to its export batch.
-   **SDK Export Configuration:** The application configures specific exporters
    (e.g., `OTLPSpanExporter`) and associates them with the corresponding
    processors/readers. The exporter is given the target endpoint and
    credentials for the OTel Collector or backend.

    ```python
    # Rigorous SDK Configuration Example (Conceptual)
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    # Define resource attributes (applied to all telemetry from this SDK instance)
    resource = Resource(attributes={ "service.name": "my-web-service", "service.version": "1.2.3" })

    # Configure OTLP exporter (gRPC to collector)
    # In production: Use secure credentials, proper endpoint resolution.
    otlp_exporter = OTLPSpanExporter(
        endpoint="otel-collector:4317", # DNS name resolved by container orchestrator
        insecure=True, # Use TLS in production!
        # timeout=5, # Specify connection/RPC timeouts
        # headers=(("auth-header", "auth-token"),) # Optional metadata/auth
    )

    # Configure Batch Span Processor
    # Exports every 5s or when 512 spans are queued, max queue size 2048, export timeout 30s
    bsp = BatchSpanProcessor(
        otlp_exporter,
        schedule_delay_millis=5000,
        max_export_batch_size=512,
        max_queue_size=2048,
        export_timeout_millis=30000
    )

    # Setup Tracer Provider
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(bsp)

    # Set global provider (usually done once at application startup)
    # opentelemetry.trace.set_tracer_provider(provider)
    # Similar setup for MeterProvider with PeriodicMetricReader and OTLPMetricExporter
    # Similar setup for LoggerProvider with BatchLogRecordProcessor and OTLPLogExporter
    ```

### 2. Transmission Phase: OTLP Network Protocol

-   **Serialization:** The SDK Exporters serialize the batched Spans, Metric
    data points, or Log records into their respective OTLP Protobuf message
    types (`ExportTraceServiceRequest`, `ExportMetricsServiceRequest`,
    `ExportLogsServiceRequest`). These requests contain the telemetry data along
    with the `Resource` information defined in the SDK.
-   **Transport:**
    -   **OTLP/gRPC (Port 4317 default):** Uses bidirectional streaming RPCs
        over HTTP/2. This is generally more efficient for continuous telemetry
        streams due to persistent connections and multiplexing.
    -   **OTLP/HTTP (Port 4318 default):** Uses standard HTTP/1.1 POST requests
        with Protobuf or JSON payloads (`Content-Type: application/protobuf` or
        `application/json`). Each request typically contains one batch. Can be
        easier to proxy and inspect but may have higher overhead per batch.
-   **Network Transit:** The serialized OTLP messages travel across the network
    from the application container/host to the Collector's designated listening
    address and port. Network latency, bandwidth, and potential packet loss are
    factors during this stage.

### 3. Reception Phase: Collector Data Ingestion

-   **Listener Binding:** The OTel Collector's `OTLP Receiver` binds to the
    specified network interface and port (e.g., `0.0.0.0:4317`). Binding to
    `0.0.0.0` allows it to accept connections directed to any IP address
    assigned to the Collector's host or container.
-   **Connection Handling & Deserialization:** The receiver component handles
    incoming network connections (TCP for gRPC, TCP for HTTP). It reads the byte
    stream, identifies the OTLP request type, and deserializes the Protobuf
    messages into the Collector's internal representation (`pdata` - Pipeline
    Data format, which closely mirrors OTLP). This involves parsing the Protobuf
    structure and validating mandatory fields. Errors during parsing (e.g.,
    corrupted data) typically result in the request being rejected and an error
    logged by the Collector.
-   **Signal Identification:** The receiver intrinsically knows the signal type
    based on the specific OTLP RPC endpoint invoked (for gRPC) or the HTTP POST
    URL path (for HTTP), as well as the Protobuf message type itself.

### 4. Processing Phase: Collector Pipeline Execution

-   **Pipeline Routing (Fan-out):** Upon successful deserialization, the OTLP
    receiver forwards the `pdata` objects to the input stage of _all_ pipelines
    declared in the `service.pipelines` section of its configuration that list
    this receiver as an input. A single receiver can feed multiple pipelines
    (e.g., traces to `traces` pipeline, metrics to `metrics` pipeline).
-   **Sequential Processor Execution:** Within each pipeline, the `pdata`
    objects flow sequentially through the defined list of processors. The order
    specified in the configuration
    (`service.pipelines.<pipeline_name>.processors`) is strictly maintained.
    Each processor receives data from the previous one (or the receiver),
    performs its function, and passes the (potentially modified) data to the
    next processor.
-   **Processor Deep Dive:**
    -   **`memory_limiter`:** Periodically checks the Collector's memory usage
        (Go runtime's `ReadMemStats`). If usage exceeds a `limit_mib` threshold,
        it begins refusing data (`check()` fails). If usage exceeds a higher
        `spike_limit_mib`, it forces garbage collection and refuses data more
        aggressively. When refusing data, it signals backpressure up the
        pipeline, potentially causing receivers to drop data or signal errors
        back to the client SDK (which might trigger retries). It aims to prevent
        OutOfMemory (OOM) kills.
    -   **`batch`:** Buffers telemetry items (spans, metrics, logs) based on
        `timeout` (e.g., 1 second) or `send_batch_size` (e.g., 8192 items).
        Whichever threshold is hit first triggers the formation and forwarding
        of a batch to the next processor. This amortizes the overhead of
        subsequent processing and export steps.
    -   **`resource`:** Ensures specific resource attributes exist or modifies
        them. Useful for standardizing attributes across different sources.
    -   **`attributes`:** Allows manipulation (insertion, update, upsert,
        deletion, hashing) of attributes on individual spans, logs, or metric
        data points based on configurable rules.
    -   **`filter`:** Includes or excludes telemetry items based on their
        attributes or properties (e.g., drop debug logs, keep only spans with
        errors).
    -   **`spanmetrics`:** Generates metrics (request counts, latencies) _from_
        span data. Requires both traces and metrics pipelines.
    -   **`tail_sampling`:** (More complex) Buffers all spans belonging to a
        trace for a certain period. Once the trace is complete (or timeout
        occurs), it evaluates policies (e.g., keep if error, keep if long
        duration, probabilistic) across the _entire trace_ before deciding
        whether to forward it or drop it. Requires significant memory.
-   **Pipeline Independence:** Each pipeline (traces, metrics, logs) operates
    largely independently, often utilizing separate goroutines and queues,
    ensuring that high volume or processing latency in one signal type does not
    block others.

### 5. Exportation Phase: Data Egress to Backends

-   **Exporter Invocation (Fan-out):** Once data traverses all processors in a
    pipeline, it is passed to _all_ exporters listed for that pipeline
    (`service.pipelines.<pipeline_name>.exporters`). The Collector fans out the
    data concurrently to each configured exporter.
-   **Exporter Mechanisms & Reliability:**
    -   **Push Exporters (e.g., `otlp`, `otlphttp`, `jaeger`):** Actively
        establish connections and send data to the configured backend endpoint.
        These exporters typically incorporate internal queuing, retry logic
        (with exponential backoff, jitter, and configurable maximum
        intervals/elapsed time), and potentially compression (`gzip`). If
        retries are exhausted (e.g., backend remains unavailable), data is
        typically dropped, and errors are logged. Success or failure of one
        exporter does not affect others operating on the same data batch.
    -   **Pull Exporters (e.g., `prometheus`):** Do not initiate connections.
        They maintain an internal cache of the latest metric data received from
        the pipeline. They expose an HTTP endpoint (e.g., `:8889/metrics`). When
        an external system (Prometheus server) sends an HTTP GET request (a
        scrape) to this endpoint, the exporter formats the cached metrics into
        the Prometheus exposition format and returns it in the HTTP response.
        The onus of scheduling, retries, and handling scrape failures lies with
        the Prometheus server.
    -   **`debug` Exporter:** Simply logs the received `pdata` objects to the
        Collector's configured output (console or file) at a specified verbosity
        level. It performs no network operations or retries.
-   **Configuration Example (`exporters` block):**

    ```yaml
    exporters:
        otlp: # Sending traces via OTLP/gRPC to Jaeger
            endpoint: jaeger-collector.observability.svc.cluster.local:4317 # K8s service DNS
            tls:
                insecure: false # Use CA certs in production
                # ca_file: /etc/certs/ca.pem
            sending_queue:
                enabled: true
                num_consumers: 5 # Parallel connections/requests
                queue_size: 1000 # Max batches buffered in memory
            retry_on_failure:
                enabled: true
                initial_interval: 5s
                max_interval: 30s
                max_elapsed_time: 5m # Stop retrying after 5 minutes

        prometheus: # Exposing metrics for Prometheus scrape
            endpoint: 0.0.0.0:8889
            namespace: my_application
            const_labels: # Add labels to all exposed metrics
                cluster: prod-us-east-1

        debug:
            verbosity: detailed # Options: basic, normal, detailed
    ```

### 6. Storage & Analysis Phase: Backend Systems

-   **Data Persistence:** Backend systems (Jaeger, Prometheus, Loki, etc.)
    receive the data from Collector exporters (or scrape it). They parse the
    data and store it in their optimized formats:
    -   **Jaeger:** Stores trace data, typically indexed by Trace ID, service
        name, operation, timestamps, and tags for efficient querying of
        individual traces and dependency analysis.
    -   **Prometheus:** Stores metrics as time series (timestamp-value pairs
        identified by metric name and label sets), optimized for time-based
        aggregation and querying using PromQL. Cardinality (number of unique
        label combinations) is a key consideration.
    -   **Loki/Elasticsearch:** Store log records, indexed by timestamps,
        labels/metadata, and potentially log content for full-text search and
        log aggregation.
-   **Querying & Visualization:** These backends provide query languages (Jaeger
    API, PromQL, LogQL) and often UIs (Jaeger UI, Grafana, Kibana) to search,
    visualize, and analyze the stored telemetry, enabling debugging, performance
    monitoring, and dashboarding.
-   **Alerting:** Systems like Prometheus (with Alertmanager) continuously
    evaluate rules against metric data, triggering alerts based on defined
    thresholds or conditions.

### 7. Systemic Considerations

-   **Resource Consumption:** The Collector itself consumes CPU, memory, and
    network bandwidth. Processors like `tail_sampling` or exporters with large
    queues can significantly increase memory usage. High data volume taxes all
    resources.
-   **Configuration Management:** Correct and consistent configuration across
    the SDK, Collector, and Backends is paramount. Errors in endpoint addresses,
    protocols, TLS settings, or pipeline definitions are common failure points.
-   **Observability of Observability:** Collector extensions like
    `health_check`, `pprof`, and `zpages`, along with the Collector's own
    metrics (if scraped), are essential for monitoring the health and
    performance of the telemetry pipeline itself.

## Anatomy of Telemetry Flow (Deep Research From OpenAI, We Keep It)

Even though below has duplicate explanations when compared to the earlier
section, we keep it because it is a deep research from OpenAI and we want to
keep it for future reference.

### Instrumentation in the Application (OpenTelemetry SDK)

OpenTelemetry instrumentation begins in the application code itself. Using the
OTel SDK (e.g. the Python SDK), developers instrument their application to
capture **traces**, **metrics**, and **logs**. Each category of telemetry is
handled as follows:

-   **Traces:** The application code uses the OpenTelemetry API to create spans
    for operations (manually or via auto-instrumentation). These spans are
    started and ended around sections of code, forming a trace (a distributed
    transaction). The OTel **Tracer** records span data (names, timings,
    attributes, context links) and maintains parent-child relationships (using
    context propagation) so that traces are coherent. When spans end, the SDK
    queues them for export via a span processor (commonly a `BatchSpanProcessor`
    that buffers spans and sends in batches)
    ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=Batch%20Processor)).
    Each span includes resource metadata (like service name) that identifies the
    source application. The spans are then transmitted out of the process by an
    **OTLP exporter** configured in the SDK, which sends trace data to the
    OpenTelemetry Collector endpoint.

-   **Metrics:** The application defines instruments (counter, histogram, etc.)
    via the OTel **Meter** API. As the app runs, these instruments record
    measurements (e.g. HTTP request counts, durations, etc.). The OTel SDK
    aggregates and periodically collects these measurements. A **MetricReader**
    (often a `PeriodicExportingMetricReader`) is set up with an **OTLP metric
    exporter** to push the aggregated metrics at intervals. This means metrics
    data is exported on a schedule (e.g. every 30s or 60s) rather than
    immediately on each update, to reduce overhead. Each metric data point is
    tagged with resource attributes (service, host, etc.) similar to traces, so
    that metrics can be attributed to the right service instance.

-   **Logs:** Application logs can be integrated into OpenTelemetry by using the
    logging SDK (or instrumentation). For example, the Python OTel SDK offers a
    logging handler or `LoggingInstrumentor` that captures logs and attaches
    tracing context (so logs can be correlated with traces)
    ([Python instrumentation sample  |  Cloud Trace  |  Google Cloud](https://cloud.google.com/trace/docs/setup/python-ot#:~:text=logHandler%20%3D%20logging,JsonFormatter)).
    These logs can then be exported via an **OTLP log exporter** to the
    Collector. In practice, logs are emitted through the standard logging
    framework (e.g. Python's `logging` module), and the OTel SDK’s handler
    intercepts and translates them into OTel log records. Like traces and
    metrics, resource attributes (service name, etc.) are attached to log
    records. The logs are then sent out via OTLP to the collector.

**Separation of concerns:** The OpenTelemetry SDK in the application is
responsible for _generating_ and _formatting_ telemetry data, but it does
minimal processing beyond that. It quickly forwards the data out-of-process
using OTLP, keeping the application overhead low. The heavy lifting (batching,
retrying, data transformation) is deferred to the Collector. This separation
ensures your application isn’t tightly coupled to any specific backend. You can
change where data is sent by reconfiguring the collector, without modifying
application code
([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=from%20any%20specific%20observability%20backend,locked%20into%20a%20single%20platform))
([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=If%20you%20ever%20decide%20to,not%20your%20entire%20application%20codebase)).
In short, the app’s SDK acts as a **telemetry source**, and the Collector will
act as the **telemetry pipeline** and exporter. This decoupling not only
prevents vendor lock-in
([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=Direct%20telemetry%20reporting%20or%20using,experiment%20with%20multiple%20backends%20simultaneously)),
but also improves reliability by offloading complex processing from the app to
the Collector.

### Telemetry Export via OTLP (OpenTelemetry Protocol)

When the SDK exports data, it uses OTLP – the OpenTelemetry Protocol – to send
traces, metrics, and logs to the Collector. **OTLP** is a standardized binary
protocol (based on Protobuf) for transmitting telemetry data between components
of the OpenTelemetry ecosystem
([A Deep Dive into the OpenTelemetry Protocol (OTLP) | Better Stack Community](https://betterstack.com/community/guides/observability/otlp/#:~:text=OTLP%20is%20a%20telemetry%20data,forwarders%2C%20and%20various%20observability%20backends)).
It was designed to be general-purpose and vendor-agnostic so that any
OTLP-compatible backend or collector can understand the data. Some key points
about OTLP:

-   **Transports:** OTLP supports both gRPC and HTTP as transport mechanisms.
    The default “native” mode is gRPC (commonly on port 4317), which provides
    efficient, bidirectional streaming. However, an HTTP/JSON or HTTP/Protobuf
    mode (often on port 4318 for JSON or binary protobuf over HTTP) is also
    supported for compatibility with systems where gRPC might not be feasible
    ([A Deep Dive into the OpenTelemetry Protocol (OTLP) | Better Stack Community](https://betterstack.com/community/guides/observability/otlp/#:~:text=,gRPC%20may%20not%20be%20ideal)).
    In practice, many SDKs default to gRPC. For example, the OTel Java agent by
    default expects to send to a gRPC endpoint (4317). If the Collector is only
    listening on HTTP (4318), you must configure the SDK exporter to use
    HTTP/protobuf instead
    ([open telemetry - ERROR io.opentelemetry.exporter.internal.grpc.OkHttpGrpcExporter - Stack Overflow](https://stackoverflow.com/questions/72099467/error-io-opentelemetry-exporter-internal-grpc-okhttpgrpcexporter#:~:text=opentelemetry,Dotel.exporter.otlp.protocol%3Dhttp%2Fprotobuf)).
    This is a common pitfall – **the protocol (gRPC vs HTTP) and port must match
    between the SDK and Collector**. Ensuring the endpoint URI (and setting like
    `OTEL_EXPORTER_OTLP_PROTOCOL`) is correct will avoid connectivity issues.

-   **Efficiency:** OTLP is built for high throughput and low latency. It uses
    compact Protobuf encoding and can batch multiple telemetry items in one
    request, which reduces overhead
    ([A Deep Dive into the OpenTelemetry Protocol (OTLP) | Better Stack Community](https://betterstack.com/community/guides/observability/otlp/#:~:text=,gRPC%20may%20not%20be%20ideal))
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=4,delivery)).
    For example, the SDK’s batch processor will bundle many spans or metrics
    into one OTLP message. OTLP’s design also allows extensibility (adding new
    fields or signal types) without breaking compatibility
    ([A Deep Dive into the OpenTelemetry Protocol (OTLP) | Better Stack Community](https://betterstack.com/community/guides/observability/otlp/#:~:text=but%20it%20also%20supports%20,gRPC%20may%20not%20be%20ideal)).

-   **Interoperability:** By using OTLP, all components speak the same language.
    The Python SDK sends OTLP, the Collector receives OTLP on its OTLP receiver,
    and the Collector can even forward OTLP to another Collector or backend.
    This eliminates the need for custom translation between formats in most
    cases. In our scenario, the application sends OTLP to the Collector, and the
    Collector’s exporters will send OTLP to Jaeger and expose Prometheus metrics
    – everything stays in open standards.

**OTLP Endpoints and configuration:** In the given setup, the application likely
knows where to send OTLP data via environment variables or code configuration.
For example, one might set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`
(for gRPC) or `http://localhost:4318` (for HTTP) depending on the Collector’s
config. The Collector’s default OTLP receiver listens on `0.0.0.0:4317` for gRPC
and `0.0.0.0:4318` for HTTP
([Introducing native support for OpenTelemetry in Jaeger | by Yuri Shkuro | JaegerTracing | Medium](https://medium.com/jaegertracing/introducing-native-support-for-opentelemetry-in-jaeger-eb661be8183c#:~:text=Notice%20that%20compared%20to%20the,previous%20releases)).
It’s possible to enable both protocols to be safe. If these endpoints don’t line
up (e.g. SDK sends gRPC to 4317 but collector only enabled 4318 HTTP, or vice
versa), telemetry will not flow. A common example is a “connection refused”
error if, say, the SDK tries gRPC on 4317 but the collector isn’t listening
there. Always double-check that the SDK’s configured protocol and the
Collector’s `otlp` receiver settings match
([open telemetry - ERROR io.opentelemetry.exporter.internal.grpc.OkHttpGrpcExporter - Stack Overflow](https://stackoverflow.com/questions/72099467/error-io-opentelemetry-exporter-internal-grpc-okhttpgrpcexporter#:~:text=opentelemetry,Dotel.exporter.otlp.protocol%3Dhttp%2Fprotobuf)).

### The OpenTelemetry Collector’s Role and Components

The OpenTelemetry Collector is a standalone service that sits between the
instrumented applications and the final observability backends. It acts as a
**telemetry pipeline** that receives data, processes it, and exports it onward.
This provides a centralized place to implement batching, retries, filtering, and
to fan-out data to multiple destinations. The Collector is often run as an agent
(one per host or container) or as a gateway (one per cluster), but in all cases
its architecture is the same. It’s essentially a **vendor-agnostic proxy** that
decouples your app from specific backends
([Getting Started with the OpenTelemetry Collector | Uptrace](https://uptrace.dev/opentelemetry/collector#:~:text=OpenTelemetry%20Collector%20serves%20as%20a,such%20as%20Uptrace%20or%20Jaeger)).

**Collector Configuration Overview:** The Collector is configured via pipelines
for each signal (traces, metrics, logs). Each pipeline defines a set of
**receivers** (entry points for data), **processors** (intermediate
transformations), and **exporters** (destinations for data). Additionally,
**extensions** provide auxiliary capabilities (health checks, monitoring, etc.)
for the Collector process itself. Below we break down each component in the
context of the provided config:

### Receivers – OTLP Receiver (gRPC/HTTP)

Receivers are how data gets **into** the Collector. In our setup, we have the
`otlp` receiver enabled for both gRPC and HTTP protocols. This means the
Collector opens up ports (e.g. 4317 for gRPC, 4318 for HTTP by default) and
**listens for incoming OTLP data**
([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=The%20OTel%20Collector%20provides%20HTTP,for%20instrumented%20services%20to%20connect)).
The instrumented Python application, which is exporting via OTLP, will connect
to this receiver.

-   The OTLP receiver understands the OTLP protocol and can ingest all three
    signal types (trace spans, metric points, log records) multiplexed over the
    same connection. As telemetry arrives, the receiver quickly parses the
    Protobuf payload into the Collector’s internal data model. According to the
    Collector’s design, it then routes each data item to the appropriate
    pipeline by signal type
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=1,components))
    (traces to the traces pipeline, etc.).

-   Because both gRPC and HTTP are enabled, the app can use either. gRPC is more
    efficient (streaming, less overhead per message), whereas OTLP/HTTP might be
    used if gRPC isn’t feasible (e.g. some environments with proxies). In either
    case, the receiver ensures the data ends up in the same format internally.
    From the perspective of the Collector’s pipeline, it doesn’t matter which
    transport was used – the data is now just “OTLP spans” or “OTLP metrics” in
    memory.

-   **Example:** If the app sends a batch of 100 spans via gRPC, the OTLP gRPC
    receiver accepts that batch and passes those spans into the traces pipeline.
    If another app sends metrics via an HTTP POST to `/v1/metrics` (the
    OTLP/HTTP endpoint), the receiver will accept and push those metrics into
    the metrics pipeline. This flexibility allows multiple apps and protocols to
    feed a single Collector. (Note: Other receivers exist for different
    protocols – e.g. Jaeger, Zipkin, Prometheus scraping, etc. – which the
    Collector could also run simultaneously
    ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=In%20addition%20to%20the%20OTel,Ray%2C%20StatsD%2C%20Prometheus%20protocols))
    ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=Metrics%20Scrapping)).
    In our case we rely solely on OTLP for inbound telemetry, simplifying the
    setup.)

### Processors – Batch, Memory Limiter, Resource

After reception, telemetry data flows through the configured **processors** in
the pipeline. Processors in OpenTelemetry Collector are optional components that
can modify or manage the data stream in-flight (for optimization or enrichment)
([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=2,it%20for%20storage%20and%20analysis)).
The provided configuration uses three key processors:

-   **Batch Processor:** The batch processor is almost always used in production
    pipelines. It **accumulates telemetry data and emits it in batches** rather
    than one item at a time. This improves throughput and reduces CPU/network
    overhead by amortizing the cost of exporting data
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=4,delivery)).
    For example, instead of making a separate export call for every single span,
    the batch processor might group 100 spans or wait up to a timeout (e.g. 5
    seconds) before sending, whichever comes first. Batching also increases the
    likelihood of compressing data efficiently and using fewer requests. The
    batch processor is analogous to the SDK’s batch span processor (and indeed
    uses similar settings like max batch size and flush timeout)
    ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=Batch%20Processor)),
    but it operates in the Collector for all signals (traces, metrics, logs). By
    buffering data briefly, it can also smooth out bursts of telemetry – if the
    app suddenly emits a spike of 1000 spans, the batcher can chunk these and
    not overwhelm the exporter or network all at once. **Reliability:** Combined
    with retries (either via built-in exporter retry mechanisms or a retry
    processor), batching helps ensure data is delivered even if the backend is
    temporarily slow or unavailable
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=4,delivery)).
    Overall, this processor optimizes performance and network usage.

-   **Memory Limiter Processor:** The memory limiter is a **safety valve** for
    the Collector’s memory usage. The Collector processes a potentially huge
    volume of data and could consume too much memory (leading to OOM) if
    incoming data outpaces the ability to export it. The memory_limiter
    processor monitors the process memory and if usage exceeds a configured
    **soft limit**, it will start dropping incoming data (i.e. applying
    backpressure)
    ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=The%20memory%20limiter%20checks%20service,any%20of%20the%20defined%20limits)).
    Dropping data is unfortunate but preferable to the Collector crashing
    completely. If memory usage hits an even higher **hard limit**, the memory
    limiter forces a garbage collection and still rejects new data until memory
    is under control
    ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=The%20memory%20limiter%20checks%20service,any%20of%20the%20defined%20limits)).
    In effect, when the soft limit is breached, the Collector tells senders “I
    can’t take more right now” (for protocols like gRPC, this backpressure
    propagates by not reading new messages, causing the SDK exporter to block or
    retry). The design assumes that SDKs or agents will handle these rejections
    gracefully – e.g. by retrying later
    ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=The%20memory%20limiter%20can%20be,down%20to%20retries%20with%20backoff)).
    This processor greatly improves stability under load: instead of the
    Collector running out of memory and crashing (losing all buffered
    telemetry), it sheds load in a controlled way. Best practice is to place the
    memory_limiter as the first processor in each pipeline, right after
    receivers, so it can start dropping data early and signal backpressure
    upstream as soon as memory limits are hit
    ([Memory Limiter processor — Splunk Observability Cloud documentation](https://docs.splunk.com/observability/gdi/opentelemetry/components/memory-limiter-processor.html#:~:text=Define%20the%20,memory_limiter))
    ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=The%20memory%20limiter%20can%20be,down%20to%20retries%20with%20backoff)).
    In a healthy system, this processor might never actually drop data; it’s
    there as a guardrail for overload scenarios.

-   **Resource Processor:** The resource processor modifies or adds **resource
    attributes** on telemetry. Resource attributes are metadata like service
    name, service version, host name, region/zone, etc., that apply to all
    spans/metrics/logs from a given source. In our pipelines, the resource
    processor can ensure that a `service.name` attribute is present and set to a
    specific value (for example, upserting “service.name=my-python-app”). It can
    also add other dimensions such as cluster or namespace, possibly drawn from
    environment variables or other existing attributes. This is useful when the
    instrumentation SDK did not supply certain resource info, or if you want to
    standardize/override it at the Collector level
    ([Resource processor — Splunk Observability Cloud documentation](https://docs.splunk.com/observability/gdi/opentelemetry/components/resource-processor.html#:~:text=The%20resource%20processor%20is%20an,with%20pipelines%20for%20more%20information)).
    For instance, if the app forgot to set service name, you can configure the
    resource processor to insert it, preventing the dreaded “unknown_service”
    label in backends. The resource processor can also delete or rename resource
    attributes (for example, stripping out an unwanted tag). In summary, this
    processor **enriches telemetry with consistent metadata** that is crucial
    for querying and filtering in observability backends. (If no changes are
    needed – e.g. the SDK already set all desired resource info – this processor
    effectively does nothing. It’s optional but often used to enforce tagging
    conventions.)

Together, these processors help ensure the telemetry is well-formed and the
pipeline is robust. The **order** is typically memory_limiter first (to control
load early), then batch (to group data for efficiency), then resource (to tag
everything before export). In some configs, resource might come earlier if you
want to ensure even the batching is grouped by certain resource, but ordering
can vary. In our case, all three are present in each pipeline
(traces/metrics/logs), which is a common best practice setup.

### Exporters – OTLP (to Jaeger), Prometheus, Debug

After processing, the data reaches the **exporters** – these are the components
that send data _out_ of the Collector to various backends or outputs. Exporters
are configured per pipeline. Let’s break down the ones in use:

-   **OTLP Exporter (to Jaeger):** In the traces pipeline, an `otlp` exporter is
    configured to send data to Jaeger. Modern Jaeger versions (>= 1.35) can
    natively ingest OTLP trace data
    ([Introducing native support for OpenTelemetry in Jaeger | by Yuri Shkuro | JaegerTracing | Medium](https://medium.com/jaegertracing/introducing-native-support-for-opentelemetry-in-jaeger-eb661be8183c#:~:text=With%20this%20new%20capability%2C%20it,1)),
    so instead of using a Jaeger-specific exporter, we use the OTLP exporter
    pointing at the Jaeger collector’s OTLP endpoint. For example, the config
    might be:

    ```yaml
    exporters:
        otlp/jaeger:
            endpoint: jaeger:4317
            tls:
                insecure: true
    ```

    This config (illustrated above) defines an OTLP exporter named “otlp/jaeger”
    sending to host `jaeger` on port `4317` (gRPC) without TLS
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=exporters%3A%20otlp%2Fjaeger%3A%20endpoint%3A%20jaeger%3A4317%20tls%3A,insecure%3A%20true)).
    When trace data reaches this exporter, the Collector opens a gRPC connection
    to the Jaeger backend and transmits the spans in OTLP format. Jaeger’s OLTP
    receiver (enabled by `COLLECTOR_OTLP_ENABLED=true` on Jaeger) will receive
    these and store them (e.g. in memory or Elasticsearch, depending on Jaeger
    setup). Essentially, the Collector is **pushing trace data** to Jaeger. This
    exporter is specific to trace data (since Jaeger is a tracing system – it
    will ignore any metrics/logs even if they were accidentally sent). By using
    OTLP, we maintain a clean, standard protocol all the way into Jaeger,
    avoiding any translation layer. _(In older setups, one might use a `jaeger`
    exporter that converts OTLP to Jaeger’s Thrift format, but that’s no longer
    necessary
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=Here%27s%20an%20sample%20configuration%20exporting,to%20a%20local%20Jaeger%20instance)).)_

-   **Prometheus Exporter:** In the metrics pipeline, the exporter is
    `prometheus`. This exporter works differently from most others: it doesn’t
    push data to an external system. Instead, it turns the Collector into a
    **Prometheus metrics endpoint** that other systems (namely a Prometheus
    Server) can scrape. When configured, the Prometheus exporter starts an HTTP
    server (on whatever `endpoint` you specify, often port 9464 or 8888) and
    exposes the collected metrics in Prometheus text format. It collects the
    metrics that have arrived via OTLP and holds onto the latest values (or
    accumulations) so that on each scrape it can present the current data. In
    other words, the Prometheus exporter is **pull-based** – the Collector
    passively waits for Prometheus to ask for data
    ([Configuration | OpenTelemetry](https://opentelemetry.io/docs/collector/configuration/#:~:text=,0%3A8889%20namespace%3A%20default)).
    This is in contrast to OTLP or other exporters which are **push-based**
    (they initiate a connection and send data out continuously
    ([Configuration | OpenTelemetry](https://opentelemetry.io/docs/collector/configuration/#:~:text=Exporters%20send%20data%20to%20one,one%20or%20more%20data%20sources))).

    **How it works:** Suppose the app sent a gauge metric “cpu_usage” every 5
    seconds via OTLP. The Collector’s prometheus exporter will keep updating the
    internal state for “cpu_usage”. If a Prometheus server scrapes the Collector
    every 15 seconds (hitting the `/metrics` endpoint of the exporter), it will
    retrieve the latest values of “cpu_usage” (and all other metrics in that
    pipeline) at scrape time. Prometheus then stores those in its time-series
    database. The exporter can also apply a `namespace` prefix to metrics (to
    avoid collisions) if configured
    ([Configuration | OpenTelemetry](https://opentelemetry.io/docs/collector/configuration/#:~:text=,0%3A8889%20namespace%3A%20default)).
    Because the data is pulled, the **timing** of when metrics are exported is
    determined by the Prometheus scrape interval, not by the Collector. The
    Collector just continuously updates the metrics in memory between scrapes.

    It’s important to note that this is the standard way to integrate
    OTel-collected metrics with Prometheus – you make the Collector act like a
    Prometheus target. If you _instead_ wanted to push metrics to a remote
    system, you could use the `prometheusremotewrite` exporter to send to a
    Prometheus remote-write endpoint
    ([Configuration | OpenTelemetry](https://opentelemetry.io/docs/collector/configuration/#:~:text=prometheus%3A%20endpoint%3A%200)),
    but in our config we’re using the scrape model. The difference is summarized
    by the Collector docs: _“Exporters can be pull or push based”_
    ([Configuration | OpenTelemetry](https://opentelemetry.io/docs/collector/configuration/#:~:text=Exporters%20send%20data%20to%20one,one%20or%20more%20data%20sources)).
    The Prometheus exporter is a pull-based exporter (the Collector doesn’t
    initiate connection to Prometheus; Prometheus connects to it), whereas the
    OTLP exporter (and most other exporters) push data out actively.

-   **Debug Exporter:** The debug exporter (formerly known as the logging
    exporter) is used for troubleshooting and development. It simply logs the
    telemetry data to the Collector’s console (stdout) or log file. In the
    config, it might be listed as `exporters: [debug]` in all pipelines. This
    means every span, metric, and log that passes through will also be printed
    out in a human-readable format. The debug exporter can be configured with a
    verbosity (e.g. `detailed` to print full data)
    ([Configuration | OpenTelemetry](https://opentelemetry.io/docs/collector/configuration/#:~:text=,debug%3A%20verbosity%3A%20detailed)).
    It’s extremely useful for **verifying that data is actually making it
    through the pipeline**. For example, if you’re not seeing data in Jaeger,
    enabling the debug exporter allows you to see if the Collector received the
    spans and what they look like. In our setup, the debug exporter is likely
    enabled for all three pipelines (traces, metrics, logs), so we will see
    console output for each signal. This exporter is not meant for production
    use (as it can be very verbose and slow), but it’s great for initial
    configuration and debugging. (Internally, as of Collector v0.86.0+, the
    “logging” exporter was replaced by the “debug” exporter name
    ([Configuration | OpenTelemetry](https://opentelemetry.io/docs/collector/configuration/#:~:text=,debug%3A%20verbosity%3A%20detailed)),
    reflecting its purpose for debugging).

To summarize exporters: the trace pipeline sends data to two exporters –
OTLP/Jaeger (pushes to Jaeger backend) and debug (logs to console). The metrics
pipeline sends to Prometheus (exposes data for scraping) and debug. The logs
pipeline sends to debug (since in this setup we might not have a separate logs
backend configured). **Multiple exporters can be attached to one pipeline**, and
the Collector will **fan-out** data to all of them. This fan-out is done
efficiently: each exporter gets a copy of the data without interfering with each
other
([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=some%20of%20the%20low%20level,paces%20affecting%20each%20other%E2%80%99s%20work)).
For instance, the debug exporter logging a span does not slow down the OTLP
exporter sending spans to Jaeger – the Collector handles them in parallel. This
design means you can safely use a debug exporter alongside real exporters, or
send one stream to two different backends, etc., for flexibility.

### Extensions – Health Check, Pprof, ZPages

Extensions are supporting services for the Collector process itself (not for the
telemetry data directly). In our configuration, we have three extensions
enabled: `health_check`, `pprof`, and `zpages`. These help with monitoring and
debugging the Collector in a production environment:

-   **Health Check Extension:** This provides a simple HTTP health endpoint (by
    default at `http://0.0.0.0:13133/`) that reports the collector’s status
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=The%20,is%20ready%20to%20accept%20data)).
    Typically it returns HTTP 200 OK if the Collector is running and ready. This
    is often used for Kubernetes liveness/readiness probes or other
    orchestrators to check if the Collector is up. If the Collector becomes
    unhealthy (in future versions, health_check may reflect internal component
    health
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=A%20new%20and%20improved%20health,their%20own%20health%20status%20updates))),
    this endpoint could be used to detect that. In current usage, it mostly
    indicates the process is alive and has finished startup. By including
    `health_check` in `service.extensions` and configuring it (or using
    defaults), you ensure the Collector can be pinged easily. This helps catch
    issues where the Collector might crash or hang – your orchestration can
    automatically restart it if the health check fails.

-   **Pprof Extension:** This enables Go’s built-in profiling server (from the
    `net/http/pprof` package) on a dedicated port (default is 1777)
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=The%20,investigate%20issues%20with%20the%20service)).
    With pprof enabled, you or developers can connect to the Collector’s pprof
    endpoint (e.g. `http://collector:1777/debug/pprof/`) to retrieve performance
    profiles: CPU profiles, heap (memory) profiles, goroutine dumps, etc. This
    is invaluable when investigating Collector performance issues or memory
    leaks in production. For instance, if the Collector’s CPU is spiking, you
    can capture a CPU profile via pprof and analyze which functions are
    consuming time. The pprof extension essentially makes the Collector
    introspectable by Go tooling without needing to modify it. This extension
    does not impact the data flowing through the collector; it’s purely for
    out-of-band debugging.

-   **Z-Pages Extension:** Z-Pages provide in-memory monitoring pages for the
    Collector’s own telemetry. When enabled (usually on an endpoint like
    `127.0.0.1:55679` by default), the Collector will host a small web UI that
    shows information about traces and metrics **inside the Collector**
    ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=The%20,in%20troubleshooting%20and%20performance%20optimization)).
    For example, you can view traces of the Collector’s operations or pipeline
    queues, and see aggregated metrics of the Collector’s performance. It’s
    somewhat analogous to an “online debug dashboard” for the Collector. This
    can be used to see active spans or recently processed traces without needing
    an external backend. Essentially, zPages give you a quick way to **verify
    what the Collector is receiving and doing** in real time. If telemetry isn’t
    making it to your backend, zPages might show if those spans at least reached
    the Collector. They also help with internal performance tuning by exposing
    metrics. In production, you might not leave zPages open publicly (since it’s
    an internal tool), but during development or in restricted environments it’s
    very useful.

All three extensions (`health_check`, `pprof`, `zpages`) are **non-intrusive** –
they don’t alter the telemetry data – but they greatly aid in running the
Collector reliably. Health checks integrate with automation, and pprof/zpages
aid developers in debugging and profiling the service. It’s a best practice to
enable at least health_check and pprof in production Collector deployments
([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=The%20,is%20ready%20to%20accept%20data))
([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=The%20,investigate%20issues%20with%20the%20service)),
so that you have a way to monitor and troubleshoot the Collector itself (after
all, the Collector is part of your observability pipeline, so it too needs to be
observable!).

## The Collector: Central Telemetry Processor

The OpenTelemetry Collector acts as a gateway between your instrumented
applications and your back-end observability systems. Its design is modular,
separating responsibilities into **receivers**, **processors**, **exporters**,
and **extensions**. Let’s break down each element of the pipeline in
[`collector-config.yaml`](../config/collector-config.yaml).

```yaml
receivers:
    otlp:
        protocols:
            grpc:
                endpoint: 0.0.0.0:4317
            http:
                endpoint: 0.0.0.0:4318

# https://opentelemetry.io/docs/collector/configuration/
# https://opentelemetry.io/docs/collector/configuration/#processors
processors:
    batch:
    # memory_limiter:
    #   check_interval: 5s
    #   limit_mib: 4000
    #   spike_limit_mib: 500
    # resource: # NOTE: if need enable this must add it below in pipelines's processors
    #   attributes:
    #     - key: service.name
    #       value: v2
    #       action: upsert

exporters:
    debug:
        verbosity: detailed
        sampling_initial: 5
        sampling_thereafter: 200

    prometheus:
        endpoint: 0.0.0.0:8889
        namespace: otel_demo
        send_timestamps: true
        resource_to_telemetry_conversion:
            enabled: true

    otlp:
        endpoint: jaeger:4317
        tls:
            insecure: true

extensions:
    health_check:
        endpoint: 0.0.0.0:13133
    pprof:
        endpoint: 0.0.0.0:1777
    zpages:
        endpoint: 0.0.0.0:55679

service:
    extensions: [health_check, pprof, zpages]
    pipelines:
        traces:
            receivers: [otlp]
            processors: [batch]
            exporters: [otlp, debug]

        metrics:
            receivers: [otlp]
            processors: [batch]
            exporters: [prometheus, debug]

        logs:
            receivers: [otlp]
            processors: [batch]
            exporters: [debug]
```

### Important Note on Exporters (Understand this first)

> The distinction between exporters in the code and in the collector config is
> important to understand. The exporters in the code are sending data to the
> collector, while the exporters in the collector config are sending data from
> the collector to a backend.

### `receivers` - Receiving Data

This file tells the **OTel Collector** exactly how to behave: where to listen
for data, how to process it, and where to send it.

```yaml
receivers:
    otlp:
        protocols:
            grpc:
                endpoint: 0.0.0.0:4317
            http:
                endpoint: 0.0.0.0:4318
```

-   **`receivers`**: This section defines _how_ the collector will _receive_
    telemetry data. It's the "incoming mail slot" configuration.
-   **`otlp`**: This specifies that the collector should expect data using the
    **O**pen**T**e**l**emetry **P**rotocol (OTLP). This is the native OTel
    format for traces, metrics, and logs.
-   **`protocols`**: OTLP data can be sent using different underlying network
    communication methods (protocols). This configures two common ones:
    -   **`grpc`**: gRPC is a modern, efficient way for programs to communicate.
        The line `endpoint: 0.0.0.0:4317` tells the collector to **listen** on
        port **4317** (on all network interfaces) for OTLP data sent using the
        gRPC protocol. This is the standard default port for OTLP/gRPC.
    -   **`http`**: HTTP is the protocol that powers the web. The line
        `endpoint: 0.0.0.0:4318` tells the collector to also **listen** on port
        **4318** (on all network interfaces) for OTLP data sent using the HTTP
        protocol. This is the standard default port for OTLP/HTTP.

**In short:** This `receivers` section makes the collector ready to accept OTel
data sent via either gRPC (on port 4317) or HTTP (on port 4318) from any
application that can reach the host machine.

### `processors` - Modifying Data In-Flight

```yaml
# https://opentelemetry.io/docs/collector/configuration/
processors:
    batch:
    # memory_limiter: # Maybe enable in future?
    #   # 80% of maximum memory
    #   limit_mib: 2000
    #   # 25% of limit upon exceeding
    #   spike_limit_mib: 500
    #   check_interval: 5s
    # resource: # NOTE: if need enable this must add it below in pipelines's processors list [...]
    #   attributes:
    #     - key: service.name
    #       value: v2
    #       action: upsert
```

-   **What are Processors?** Once the collector _receives_ data (via the
    `receivers`), it can optionally _process_ it before _exporting_ it.
    Processors act like stations on an assembly line; they modify the telemetry
    data passing through. This could involve:
    -   Adding extra information (like the environment it's running in).
    -   Filtering out unwanted data (e.g., noisy logs).
    -   Sampling traces (only keeping a percentage of traces to reduce volume).
    -   Batching data for more efficient sending.
-   **`batch` Processor:**
    -   **Purpose:** This is one of the most common and important processors.
        Network communication is often more efficient when sending data in
        larger chunks rather than many small pieces. The `batch` processor
        collects individual spans (parts of traces), metric data points, or log
        entries as they arrive and groups them into batches. It then sends these
        batches downstream to the exporters.
    -   **Why Use It:** Sending data piece-by-piece can create a lot of network
        overhead (each send requires setup and teardown). Batching reduces this
        overhead, leading to better performance for both the collector and the
        receiving systems (exporters). It also reduces the number of outgoing
        requests.
    -   **Configuration:** In this file, the `batch:` line is present, but it
        doesn't have any specific configuration options underneath it (like
        `send_batch_size` or `timeout`). This means it's using the _default_
        settings for the batch processor provided by the OTel Collector. These
        defaults are generally sensible for common use cases.
-   **Other Processors (Potential Future Use):**
    -   **`memory_limiter`:**
        -   **Purpose:** This processor helps prevent the collector from running
            out of memory if data arrives faster than it can be processed and
            exported. It monitors the collector's memory usage.
        -   **How it would work:** If enabled, `limit_mib: 2000` would set a
            memory limit (e.g., 2000 MiB). If usage exceeds this, the processor
            would start dropping data to relieve pressure. `spike_limit_mib`
            adds a buffer for sudden spikes, and `check_interval` defines how
            often to check memory usage.
        -   **Relevance:** Useful in high-throughput environments to ensure
            collector stability.
    -   **`resource`:**
        -   **Purpose:** Telemetry data often includes "resource attributes"
            describing the _source_ of the data (e.g., the application name,
            version, cloud region). This processor allows you to modify these
            attributes.
        -   **How it would work:** If enabled, the example configuration
            (`attributes: ... action: upsert`) would ensure that every piece of
            telemetry data passing through has a resource attribute
            `service.name` set to `v2`. If the attribute already exists, it
            updates it (`upsert`); if not, it adds it.
        -   **Relevance:** Useful for standardizing identifying information
            across all telemetry data originating from a specific collector
            instance or environment. The comment
            `NOTE: if need enable this must add it below in pipelines's processors list [...]`
            is crucial - just defining a processor here isn't enough; it must
            also be explicitly added to the relevant pipeline(s) in the
            `service` section to be activated.

#### Difference between configs in SDK/app level vs collector config

Let's just use `batch` as an example here. In SDK level, there is batch, and in
collector config, there is also batch. There are two separate batch mechanisms
in the OpenTelemetry setup:

1. **SDK-level batching**: This happens in your application code via the
   OpenTelemetry SDK. The SDK's batch processor (like `BatchSpanProcessor` for
   traces) collects telemetry data within your application process before
   sending it to the collector.

2. **Collector-level batching**: This happens in the OpenTelemetry Collector
   after it receives data from your application. The collector's batch processor
   collects telemetry before forwarding it to backend systems.

The key differences are:

-   **SDK batch processor**: Batches data from your application to the collector

    -   Configured in your application code or environment variables (e.g.,
        `OTEL_BSP_MAX_EXPORT_BATCH_SIZE`)
    -   Controls how efficiently your application sends data to the collector
    -   Reduces network overhead between your app and the collector

-   **Collector batch processor**: Batches data from the collector to backend
    systems
    -   Configured in the collector's config file (`collector-config.yaml`)
    -   Controls how efficiently the collector sends data to backends like
        Jaeger/Prometheus
    -   Reduces network overhead between the collector and backends

Both batch processors work independently and can have different configurations.
The collector's batch processor can override or supplement the SDK's batching
behavior, providing an additional layer of optimization for forwarding data to
backends.

### `exporters` - Sending Data Out

```yaml
exporters:
    debug:
        verbosity: detailed
        sampling_initial: 5
        sampling_thereafter: 200

    prometheus:
        endpoint: 0.0.0.0:8889
        namespace: otel_demo
        send_timestamps: true
        resource_to_telemetry_conversion:
            enabled: true

    otlp:
        endpoint: jaeger:4317
        tls:
            insecure: true
```

-   **What are Exporters?** After data has been received and potentially
    processed, exporters are responsible for _sending_ it to its final
    destination(s). These destinations are typically backend systems designed
    for storing, visualizing, and analyzing telemetry data.
-   **`debug` Exporter:**
    -   **Purpose:** This is primarily used for debugging and development.
        Instead of sending data to a real backend, it prints the telemetry data
        it receives directly to the collector's own console output (standard out
        or standard error).
    -   **Configuration:**
        -   `verbosity: detailed`: This tells the exporter to print the _full_
            contents of the traces, metrics, and logs it receives. Other options
            might be `basic` or `normal` for less output. `detailed` is very
            useful when troubleshooting to see exactly what data the collector
            is handling.
        -   `sampling_initial: 5`: Print the first 5 batches of data received in
            detail.
        -   `sampling_thereafter: 200`: After the initial samples, only print
            one out of every 200 batches received. This prevents the console
            from being flooded with excessive output in long-running or
            high-traffic scenarios while still providing occasional glimpses of
            the data flow.
    -   **Relevance:** Excellent for verifying that the collector is receiving
        data as expected and understanding the structure of the data _before_
        configuring complex backends.
-   **`prometheus` Exporter:**
    -   **Purpose:** Prometheus is a very popular open-source system for
        collecting and querying time-series _metrics_. It works on a "pull"
        model: Prometheus itself periodically connects to configured targets
        (like this exporter) and "scrapes" (requests) the latest metric values.
        This exporter makes the OTel Collector's received metrics available for
        a Prometheus server to scrape.
    -   **Configuration:**
        -   `endpoint: 0.0.0.0:8889`: This tells the `prometheus` exporter
            _within the collector_ to start its own tiny web server,
            **listening** on port **8889** (on all network interfaces of the
            collector's host/container). When a Prometheus server connects to
            this address (`<collector_ip>:8889/metrics`), this exporter will
            respond with the current metric data in the format Prometheus
            understands. It's the reverse of a receiver; here the collector
            _provides_ an endpoint for something else (Prometheus) to connect
            _to_.
        -   `namespace: otel_demo`: Prefixes all metric names exposed by this
            exporter with `otel_demo_`. This helps avoid naming collisions if
            Prometheus is scraping metrics from multiple sources.
        -   `send_timestamps: true`: Includes the original timestamp of the
            metric data point when exposing it to Prometheus.
        -   `resource_to_telemetry_conversion: enabled: true`: Attempts to
            convert OTel resource attributes (like `service.name`) into
            Prometheus labels attached to the metrics, allowing for richer
            filtering and aggregation in Prometheus.
    -   **Relevance:** This is the standard way to feed metrics collected by
        OTel into a Prometheus monitoring stack.
-   **`otlp` Exporter:**
    -   **Purpose:** This exporter sends telemetry data _out_ using the standard
        OTLP protocol (just like the `otlp` _receiver_ accepted data _in_ using
        OTLP). It's designed to send data to another OTel Collector or any
        backend system that understands OTLP (like Jaeger, Tempo, Grafana Cloud,
        etc.).
    -   **Configuration:**
        -   `endpoint: jaeger:4317`: This specifies the destination address for
            the OTLP data. Unlike the `0.0.0.0` used for _listening_, this is a
            specific target. `jaeger:4317` likely means: "Send the data to a
            host named `jaeger` on port `4317`." In a containerized environment
            (like Docker Compose or Kubernetes, which are hinted at by the
            filenames in your workspace), `jaeger` is often the service name of
            another container running the Jaeger tracing system. That Jaeger
            instance would be _listening_ on its port 4317 (likely configured to
            receive OTLP/gRPC). Push based: Data is pushed over the OTLP
            protocol to the Jaeger service running on port 4317 (as defined in
            your exporter configuration).
        -   `tls: insecure: true`: TLS (Transport Layer Security) is the
            standard for encrypting network communication (like HTTPS for
            websites). This setting `insecure: true` explicitly _disables_ TLS
            encryption for the connection _from the collector to Jaeger_. This
            is common in development or internal networks where encryption might
            be deemed unnecessary overhead, but **it should generally NOT be
            used in production environments handling sensitive data over
            untrusted networks.** In production, you would configure TLS
            properly with certificates for secure communication.
    -   **Relevance:** This is the primary way to forward OTel data to
        OTel-native backends or other collectors in a pipeline. Here, it's
        specifically configured to send data (likely traces, as Jaeger is a
        tracing system) to a Jaeger backend.

#### Docker DNS Resolution And Why Hostname is Jaeger?

In Docker Compose environments, the service name automatically becomes the
hostname that other services can use to reach that container. This is a key
feature of Docker's built-in DNS resolution for custom networks.

When you have this in your collector configuration:

```yaml
exporters:
    otlp:
        endpoint: jaeger:4317
        tls:
            insecure: true
```

And these services defined in your docker-compose file:

```yaml
services:
    otel-collector:
        # configuration...
        networks:
            - otel-demo

    jaeger:
        # configuration...
        networks:
            - otel-demo
```

Docker automatically creates DNS entries for each service, allowing them to
communicate using the service name as a hostname. So `jaeger:4317` in the
collector config means "connect to port 4317 on the container running the jaeger
service."

This works because:

1. Both containers are on the same Docker network (`otel-demo`)
2. Docker provides automatic DNS resolution within custom networks
3. Service names in docker-compose.yml become hostnames in that network

This is much more convenient than using IP addresses because:

-   Container IPs can change when containers restart
-   You don't need to manually discover or configure IP addresses
-   It works the same in development and production environments

If you were to deploy this in Kubernetes instead of Docker Compose, the same
concept applies - service names would be used as hostnames to communicate
between pods in the same namespace.

#### Debug Exporter

The `debug` exporter in the collector configuration is essentially the
equivalent of adding console logging in your application code. They serve
similar purposes but operate at different points in the telemetry pipeline.

##### Debug Exporter in Collector Config

The `debug` exporter in your collector configuration (which you can see in the
config as `exporters: [debug]` for each pipeline) does the following:

```yaml
exporters:
    debug:
        verbosity: detailed
        sampling_initial: 5
        sampling_thereafter: 200
```

1. **Purpose**: Prints telemetry data to the collector's console/stdout for
   debugging and verification
2. **Configuration**:

    - `verbosity: detailed` - Shows the full content of spans, metrics, and logs
    - `sampling_initial: 5` - Prints the first 5 batches of data in detail
    - `sampling_thereafter: 200` - After that, only prints 1 out of every 200
      batches

3. **Usage examples**:

    - Verifying that data is reaching the collector
    - Troubleshooting why data might not be appearing in backends like Jaeger
    - Inspecting the format and content of telemetry as it passes through the
      collector

4. **Where output appears**: In the collector's logs/console (e.g., if running
   in Docker, you'd see it with `docker logs otel-collector`)

##### Console Logging in Application Code

When you add console logging in your application's instrumentation code:

1. **Purpose**: Prints telemetry data to your application's stdout for debugging
2. **Implementation**: Might use a console exporter like:

    ```python
    # Python example
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    console_exporter = ConsoleSpanExporter()
    processor = SimpleSpanProcessor(console_exporter)
    tracer_provider.add_span_processor(processor)
    ```

3. **Usage examples**:

    - Debugging during development
    - Verifying spans are being created correctly
    - Checking if context propagation is working

4. **Where output appears**: In your application's console output

##### Key Differences

1. **Location in pipeline**:

    - App console logging: Shows data as it's generated in your application
    - Collector debug exporter: Shows data after it's been received and
      processed by the collector

2. **Detail and format**:

    - App logging: Format depends on the SDK's implementation
    - Collector debug: Consistent format with configurable verbosity

3. **Sampling control**:
    - App logging: Depends on how you configure it (often shows all spans)
    - Collector debug: Has built-in sampling to prevent overwhelming logs

##### When to Use Each

-   **Application console logging**: During initial development to confirm your
    instrumentation is working correctly
-   **Collector debug exporter**: When testing the full pipeline to verify data
    is flowing through the collector correctly

In practice, the collector's debug exporter is more powerful because:

1. It can show all three signal types (traces, metrics, logs)
2. It shows data after any transformations by the collector's processors
3. It has built-in sampling to manage log volume in busy systems
4. It can confirm the data successfully made it to the collector

Both serve the purpose of logging telemetry for debugging, just at different
stages of the flow.

### `extensions` - Adding Auxiliary Capabilities

```yaml
extensions:
    health_check:
        endpoint: 0.0.0.0:13133
    pprof:
        endpoint: 0.0.0.0:1777
    zpages:
        endpoint: 0.0.0.0:55679
```

-   **What are Extensions?** Extensions add functionality to the collector that
    isn't directly part of the data processing pipeline (receive -> process ->
    export). They often provide ways to monitor the collector itself or expose
    diagnostic interfaces.
-   **`health_check` Extension:**
    -   **Purpose:** Provides a simple way to check if the collector process is
        running and healthy. Monitoring systems or orchestrators (like
        Kubernetes) can query this endpoint to determine if the collector is
        operational.
    -   **Configuration:** `endpoint: 0.0.0.0:13133` tells the health check
        extension to **listen** on port **13133** (on all interfaces). If you
        make an HTTP request to `http://<collector_ip>:13133`, it will respond
        with a status code indicating health (e.g., `200 OK` if healthy).
    -   **Relevance:** Essential for automated monitoring and ensuring the
        collector is running correctly.
-   **`pprof` Extension:**
    -   **Purpose:** The OTel Collector is written in the Go programming
        language. `pprof` is Go's standard tool for profiling performance (CPU
        usage, memory allocation). Enabling this extension allows developers or
        operators to connect to the collector and gather detailed performance
        profiles.
    -   **Configuration:** `endpoint: 0.0.0.0:1777` tells the pprof extension to
        **listen** on port **1777** (on all interfaces), exposing the profiling
        data endpoints. Tools can then connect to this port to request profiles.
    -   **Relevance:** Useful for diagnosing performance bottlenecks _within the
        collector itself_ if it seems to be consuming too many resources.
-   **`zpages` Extension:**
    -   **Purpose:** zPages are web-based diagnostic pages, originally developed
        at Google, that provide visibility into the internal state of running
        processes. For the collector, this can show information about configured
        pipelines, connected clients, internal metrics, etc.
    -   **Configuration:** `endpoint: 0.0.0.0:55679` tells the zPages extension
        to **listen** on port **55679** (on all interfaces). You can then open
        `http://<collector_ip>:55679` in a web browser to view the diagnostic
        pages.
    -   **Relevance:** Provides a human-friendly way to inspect the collector's
        internal state for debugging and understanding its behavior without
        needing specialized tools (like pprof).

### `service` - Tying Everything Together

```yaml
service:
    extensions: [health_check, pprof, zpages]
    pipelines:
        traces:
            receivers: [otlp]
            processors: [batch]
            exporters: [otlp, debug]

        metrics:
            receivers: [otlp]
            processors: [batch]
            exporters: [prometheus, debug]

        logs:
            receivers: [otlp]
            processors: [batch]
            exporters: [debug]
```

-   **What is the `service` Section?** This is the conductor of the orchestra.
    It defines _which_ components (receivers, processors, exporters, extensions)
    are actually _active_ and _how they are connected_.
-   **`extensions: [health_check, pprof, zpages]`:** This line explicitly
    _enables_ the extensions that were defined earlier in the `extensions:`
    block. If an extension was defined but not listed here, it wouldn't be
    started.
-   **`pipelines`:** This is the core of the service definition. A pipeline
    defines the path data takes from input to output for a specific _type_ of
    telemetry signal (traces, metrics, or logs). You can define multiple
    pipelines if needed, but here there's one for each signal type.
    -   **`traces` Pipeline:**
        -   `receivers: [otlp]`: This pipeline gets its input data from the
            receiver named `otlp` (which we defined earlier to listen on ports
            4317 and 4318).
        -   `processors: [batch]`: The trace data received will pass through the
            `batch` processor. If we had uncommented the `resource` processor
            earlier, we would add it here like `processors: [batch, resource]`
            (order matters!).
        -   `exporters: [otlp, debug]`: After processing, the trace data is sent
            to _two_ destinations: the `otlp` exporter (which sends it to
            `jaeger:4317`) and the `debug` exporter (which prints it to the
            console).
    -   **`metrics` Pipeline:**
        -   `receivers: [otlp]`: Also receives data from the `otlp` receiver.
            Note that the same receiver can handle multiple signal types if
            configured to do so (OTLP natively supports traces, metrics, and
            logs).
        -   `processors: [batch]`: Metric data also goes through the `batch`
            processor.
        -   `exporters: [prometheus, debug]`: Metric data is sent to the
            `prometheus` exporter (making it available on port 8889 for
            scraping) and the `debug` exporter.
    -   **`logs` Pipeline:**
        -   `receivers: [otlp]`: Receives logs from the `otlp` receiver.
        -   `processors: [batch]`: Log data also goes through the `batch`
            processor.
        -   `exporters: [debug]`: Log data is _only_ sent to the `debug`
            exporter in this configuration. It's not being sent to Prometheus
            (which is primarily for metrics) or the `otlp` exporter (though it
            could be, if Jaeger or another backend was configured to receive
            OTLP logs).

### Summary

This configuration file sets up an OTel Collector that:

1.  **Listens** for OTLP data (traces, metrics, logs) via both gRPC (port 4317)
    and HTTP (port 4318) using the `otlp` receiver.
2.  **Processes** all received data by batching it for efficiency using the
    `batch` processor.
3.  **Exports** the data based on its type:
    -   **Traces:** Sent via OTLP to a Jaeger instance (at `jaeger:4317`) AND
        printed to the console (`debug`).
    -   **Metrics:** Made available for a Prometheus server to scrape (on
        port 8889) AND printed to the console (`debug`).
    -   **Logs:** Only printed to the console (`debug`).
4.  **Enables** supporting services (`extensions`): a health check (port 13133),
    performance profiling (port 1777), and diagnostic web pages (port 55679).

This setup is typical for a development or testing environment where you want to
send traces to Jaeger, metrics to Prometheus, and see all data easily via the
debug output, while also having tools to check the collector's health and
performance.

## References

1. OpenTelemetry Collector as a vendor-agnostic pipeline
   ([Getting Started with the OpenTelemetry Collector | Uptrace](https://uptrace.dev/opentelemetry/collector#:~:text=OpenTelemetry%20Collector%20serves%20as%20a,such%20as%20Uptrace%20or%20Jaeger))
   ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=Direct%20telemetry%20reporting%20or%20using,experiment%20with%20multiple%20backends%20simultaneously))
2. OpenTelemetry Protocol (OTLP) overview and characteristics
   ([A Deep Dive into the OpenTelemetry Protocol (OTLP) | Better Stack Community](https://betterstack.com/community/guides/observability/otlp/#:~:text=OTLP%20is%20a%20telemetry%20data,forwarders%2C%20and%20various%20observability%20backends))
   ([A Deep Dive into the OpenTelemetry Protocol (OTLP) | Better Stack Community](https://betterstack.com/community/guides/observability/otlp/#:~:text=,gRPC%20may%20not%20be%20ideal))
3. Collector processors (batch, memory_limiter, resource) and their benefits
   ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=4,delivery))
   ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=The%20memory%20limiter%20checks%20service,any%20of%20the%20defined%20limits))
   ([Resource processor — Splunk Observability Cloud documentation](https://docs.splunk.com/observability/gdi/opentelemetry/components/resource-processor.html#:~:text=The%20resource%20processor%20is%20an,with%20pipelines%20for%20more%20information))
4. Collector exporters and modes (push vs pull, OTLP vs Prometheus)
   ([Configuration | OpenTelemetry](https://opentelemetry.io/docs/collector/configuration/#:~:text=Exporters%20send%20data%20to%20one,one%20or%20more%20data%20sources))
   ([Configuration | OpenTelemetry](https://opentelemetry.io/docs/collector/configuration/#:~:text=,0%3A8889%20namespace%3A%20default))
5. Collector extensions for health, profiling, and debugging
   ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=The%20,is%20ready%20to%20accept%20data))
   ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=The%20,in%20troubleshooting%20and%20performance%20optimization))
6. Common OTLP configuration pitfalls (4317 vs 4318, protocol setting)
   ([open telemetry - ERROR io.opentelemetry.exporter.internal.grpc.OkHttpGrpcExporter - Stack Overflow](https://stackoverflow.com/questions/72099467/error-io-opentelemetry-exporter-internal-grpc-okhttpgrpcexporter#:~:text=opentelemetry,Dotel.exporter.otlp.protocol%3Dhttp%2Fprotobuf))
7. Jaeger OTLP exporter configuration example
   ([A Beginner's Guide to the OpenTelemetry Collector | Better Stack Community](https://betterstack.com/community/guides/observability/opentelemetry-collector/#:~:text=exporters%3A%20otlp%2Fjaeger%3A%20endpoint%3A%20jaeger%3A4317%20tls%3A,insecure%3A%20true))
   and native support in Jaeger
