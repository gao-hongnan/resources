# Flow

```{contents}
:local:
```

## 1. Diagrams

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

```{mermaid}
:zoom:

flowchart TB
    %% Main application entry point
    App["Application Code"] --> |"(1) initialize_telemetry()"| Init["Telemetry Initialization"]
    Init --> |"(2) Thread-safe singleton"| Telemetry["Telemetry Facade (Singleton)"]

    %% Builder process
    Telemetry --> |"(3) Create"| Builder["TelemetryBuilder"]
    Builder --> |"(4a) build_resource()"| ResourceFactory["ResourceFactory"]
    Builder --> |"(4b) build_propagator()"| PropagatorFactory["PropagatorFactory"]
    Builder --> |"(4c) build_tracing()"| TracingFactories["Tracing Factories"]
    Builder --> |"(4d) build_metrics()"| MetricsFactories["Metrics Factories"]
    Builder --> |"(4e) build_logging()"| LoggingSetup["Logging Setup"]

    %% Component creation
    Builder --> |"(5) build()"| Components["TelemetryComponents"]

    %% Component setup
    Components --> |"(6) setup_all()"| SetupFlow["Component Setup Process"]

    %% Detailed component setup
    subgraph "Component Setup Flow"
        Setup1["PropagatorComponent.setup()"] --> Setup2["TracingComponent.setup()"]
        Setup2 --> Setup3["MetricsComponent.setup()"]
        Setup3 --> Setup4["LoggingComponent.setup()"]

        Setup2 --> |"Create"| Sampler["Sampler"]
        Setup2 --> |"Create"| SpanProc["SpanProcessor"]
        SpanProc --> |"Uses"| SpanExp["SpanExporter"]

        Setup3 --> |"Create"| MetricRead["MetricReader"]
        MetricRead --> |"Uses"| MetricExp["MetricExporter"]
    end

    %% Instrumentation flows
    subgraph "Application Instrumentation"
        %% Tracing API
        TracingAPI["Tracing API"] --> |"Create spans"| SpanCreation["Span Creation"]
        SpanCreation --> |"Manage spans"| SpanLifecycle["Span Lifecycle"]
        SpanLifecycle --> |"Complete spans"| SpanEnd["Span Completion"]

        %% Metrics API
        MetricsAPI["Metrics API"] --> |"Create instruments"| MetricInst["Metric Instruments"]
        MetricInst --> |"Record values"| MetricRecord["Metric Recording"]

        %% Logging API
        LoggingAPI["Logging API"] --> |"Create logs"| LogRecord["Log Records"]

        %% Context Propagation
        ContextAPI["Context Propagation API"] --> |"Transfer context"| ContextCarrier["Context Carrier"]
    end

    %% Telemetry Facade connects to Application Instrumentation
    Telemetry --> |"(7) Provide APIs"| ApplicationInstrumentation["Application Instrumentation"]

    %% Data processing flows
    SpanEnd --> |"(8a) Process spans"| ProcessingPipeline["Span Processing Pipeline"]
    MetricRecord --> |"(8b) Aggregate metrics"| MetricPipeline["Metric Processing Pipeline"]
    LogRecord --> |"(8c) Format logs"| LogPipeline["Log Processing Pipeline"]

    %% Processing details
    subgraph "Span Processing Pipeline"
        SpanProcessor["Span Processor"] --> |"Process"| SpanExporter["Span Exporter"]
    end

    subgraph "Metric Processing Pipeline"
        MeterProvider["Meter Provider"] --> |"Collect"| MetricReader["Metric Reader"] --> MetricExporter["Metric Exporter"]
    end

    subgraph "Log Processing Pipeline"
        TraceLogger["Trace-Context Logger"] --> |"Format"| LogHandler["Log Handler"]
    end

    %% Export flows
    SpanExporter --> |"(9a) Export spans"| OTelCollector["OpenTelemetry Collector"]
    MetricExporter --> |"(9b) Export metrics"| OTelCollector
    LogHandler --> |"(9c) Export logs"| OTelCollector

    %% Context propagation between services
    ContextCarrier --> |"(10) Transfer context"| Service2["Downstream Service"]
    Service2 --> |"(11) Extract context"| Service2Context["Downstream Context"]
    Service2Context --> |"(12) Maintain continuity"| Service2Spans["Downstream Spans"]

    %% Backend systems
    OTelCollector --> |"(13) Process data"| OTelBackends["Observability Backends"]

    subgraph "Observability Backends"
        JaegerUI["Jaeger UI"]
        Prometheus["Prometheus"]
        Loki["Loki"]
    end

    %% Visualization layer
    JaegerUI --> |"(14a) Visualize traces"| Dashboards["Dashboards"]
    Prometheus --> |"(14b) Visualize metrics"| Dashboards
    Loki --> |"(14c) Visualize logs"| Dashboards

    %% Application shutdown
    App --> |"(15) Application shutdown"| Shutdown["Telemetry Shutdown"]
    Shutdown --> |"(16) shutdown_all()"| ShutdownFlow["Component Shutdown Process"]

    subgraph "Component Shutdown Flow"
        Shutdown1["TracingComponent.shutdown()"] --> Shutdown2["MetricsComponent.shutdown()"]
        Shutdown2 --> Shutdown3["LoggingComponent.shutdown()"]
        Shutdown3 --> Shutdown4["PropagatorComponent.shutdown()"]
    end

    %% Styling
    classDef factory fill:#f9d77e,stroke:#333,stroke-width:1px
    classDef component fill:#a8d5ba,stroke:#333,stroke-width:1px
    classDef pipeline fill:#f49e7e,stroke:#333,stroke-width:1px
    classDef api fill:#a9cce3,stroke:#333,stroke-width:1px
    classDef backend fill:#c39bd3,stroke:#333,stroke-width:1px

    class ResourceFactory,PropagatorFactory,TracingFactories,MetricsFactories factory
    class Components,SetupFlow,ShutdownFlow component
    class ProcessingPipeline,MetricPipeline,LogPipeline pipeline
    class TracingAPI,MetricsAPI,LoggingAPI,ContextAPI api
    class OTelBackends,JaegerUI,Prometheus,Loki backend
```

## 2. System Architecture Overview

To understand how `cryostorm` fits in, let's look at the typical components
involved in collecting and viewing telemetry data.

### 2.1 Application Layer (Your Code + `cryostorm`)

This is where your application logic lives and where telemetry data originates.

-   **Application Code:** Your specific business logic (e.g., a web request
    handler, a data processing task).
-   **`cryostorm` Telemetry Facade (`Telemetry` class):** The main interface
    provided by _this_ library. You interact with this object to initialize
    telemetry and generate data (spans, metrics, logs). It hides much of the
    underlying OTel complexity.
-   **OpenTelemetry SDK (Python Libraries):** The core OpenTelemetry libraries
    that `cryostorm` uses behind the scenes. These implement the OTel
    specification.
    -   **SDK Processors:** Components within the SDK that process telemetry
        data before it's sent out. Common examples include:
        -   `BatchSpanProcessor`: Groups multiple spans together before sending
            to improve efficiency.
        -   `SimpleSpanProcessor`: Sends each span individually (less efficient,
            often used for debugging).
    -   **SDK Exporters:** Components within the SDK responsible for formatting
        and sending the processed telemetry data to a destination (usually the
        OTel Collector). Examples include:
        -   `OTLPSpanExporter`: Sends data using the OpenTelemetry Protocol
            (OTLP) format.
        -   `ConsoleSpanExporter`: Prints data to the console (useful for
            debugging).
-   **Resource:** Represents the entity producing telemetry (e.g., your
    service). It includes identifying attributes like service name, version, and
    environment.

### 2.2 OpenTelemetry Collector (The Data Hub)

The **OpenTelemetry Collector (OTel Collector)** is a separate, standalone
application (often run as a container, see `docker-compose-local.yml`). It acts
as a central hub for receiving, processing, and exporting telemetry data. It's
highly recommended in most production setups.

-   **Why use a Collector?**

    -   **Decoupling:** Your application only needs to know how to send data to
        the Collector (using OTLP). The Collector handles sending it to various
        backend systems (Jaeger, Prometheus, etc.). You can change backends
        without changing your application code.
    -   **Efficiency:** The Collector can batch data more effectively, reducing
        network load.
    -   **Processing:** It can perform advanced processing like filtering,
        adding extra attributes (e.g., Kubernetes metadata), tail-based sampling
        (making sampling decisions based on the _entire_ trace), and calculating
        rates.
    -   **Resilience:** It can buffer data if a backend is temporarily
        unavailable.

-   **Collector Components:**
    -   **Receivers:** Listen for incoming data from applications (e.g., `otlp`
        receiver listens for OTLP data on ports 4317/4318).
    -   **Processors:** Modify or filter data as it flows through the Collector
        (e.g., `batch` processor for further batching, `memory_limiter` to
        prevent crashes under heavy load).
    -   **Exporters:** Send processed data to final destinations (e.g., `otlp`
        exporter to send traces to Jaeger, `prometheus` exporter to expose
        metrics for Prometheus to scrape).
    -   **Extensions:** Provide additional capabilities like health checks
        (`health_check`) or performance profiling (`pprof`).
    -   **Service Pipelines:** Define how data flows from receivers through
        processors to exporters for each signal type (traces, metrics, logs).

_(See Section 8 for a detailed breakdown of the `collector-config.yaml` file)_

### 2.3 Backend Systems (Storage & Visualization)

These are the final destinations where telemetry data is stored, queried, and
visualized.

-   **Jaeger:** An open-source distributed tracing system. It stores trace data
    received from the Collector and provides a Web UI to search and visualize
    request flows across services.
-   **Prometheus:** An open-source time-series database and monitoring system.
    It periodically "scrapes" (pulls) metrics data from configured targets (like
    the OTel Collector's Prometheus exporter endpoint) and stores it. It has its
    own query language (PromQL) and basic UI.
-   **Loki (Future):** An open-source log aggregation system, often used with
    Prometheus and Grafana. It's designed to efficiently store and query logs
    based on labels (similar to Prometheus). _Note: The current setup uses the
    `debug` exporter for logs, sending them to the Collector's console output,
    but Loki could be added._
-   **Grafana:** An open-source visualization and analytics platform. It
    connects to various data sources (like Jaeger, Prometheus, Loki) to create
    unified dashboards, visualize trends, and set up alerts.

_(See Section 7 for how these are run using `docker-compose-local.yml`)_

---

## 3. Core Concepts and Code Structure (`cryostorm` Library)

This section dives into the specific Python code components provided by the
`cryostorm` library.

### 3.1 Key Files and Their Purpose

-   `telemetry.py`: Contains the main `Telemetry` facade class, the entry point
    for using the library. Also includes the `TelemetryBuilder` and
    `TelemetryComponents`.
-   `settings.py`: Defines Pydantic models (`TelemetrySettings`,
    `TracingConfig`, etc.) for configuring the library, primarily through
    environment variables.
-   `interface.py`: Defines base abstract classes (`TelemetryComponent`,
    `Factory`) used throughout the library.
-   `constants.py`: Defines Enumerations (Enums) for configuration options
    (e.g., `ExporterType`, `ProcessorType`, `EnvironmentType`).
-   `resource.py`: Contains `ResourceFactory` for creating the OpenTelemetry
    `Resource` object that identifies your service.
-   `propagator.py`: Contains `PropagatorFactory` and `PropagatorComponent` for
    setting up context propagation (linking traces across services).
-   `trace.py`: Contains `SpanExporterFactory`, `SpanProcessorFactory`, and
    `TracingComponent` for setting up the tracing pipeline.
-   `metric.py`: Contains `MetricExporterFactory`, `MetricReaderFactory`, and
    `MetricsComponent` for setting up the metrics pipeline.
-   `log.py`: Contains `LogExporterFactory`, `LogProcessorFactory`, and
    `LoggingComponent` for setting up the logging pipeline.
-   `sampler.py`: Contains `SamplerFactory` for creating trace samplers
    (determining which traces to record).
-   `types_.py`: Defines type hints and generics used within the library.
-   `__init__.py`: Makes the directory a Python package (currently empty).

### 3.2 Central Facade: `Telemetry` Class (`telemetry.py`)

This is the **primary class** you will interact with.

-   **Purpose:** To provide a single, unified, and simplified interface for
    initializing and using OpenTelemetry tracing, metrics, and logging within
    your application. It hides the complexity of configuring and connecting the
    various underlying OTel SDK components.
-   **Singleton Pattern:** The `Telemetry` class is implemented as a
    **thread-safe singleton**.
    -   **What is a Singleton?** A design pattern that ensures a class has only
        _one_ instance throughout the application's lifetime and provides a
        global point of access to it.
    -   **Why use it here?** Telemetry setup is typically done once per
        application process. Using a singleton prevents accidental multiple
        initializations (which can cause issues) and makes it easy to access the
        configured telemetry tools (tracer, meter, logger) from anywhere in your
        code via `Telemetry.get_instance()`.
    -   **Thread-Safety:** The `threading.RLock` ensures that even if multiple
        threads try to initialize or access the instance concurrently, the
        process remains safe and consistent.
-   **Initialization:**
    -   You typically create the instance once using
        `Telemetry.from_settings(settings_object)`.
    -   Internally, it uses `TelemetryBuilder` to construct all necessary
        components (`TracingComponent`, `MetricsComponent`, etc.) based on the
        provided `TelemetrySettings`.
    -   It then calls `setup_all()` on the components to perform the actual OTel
        SDK configuration (e.g., setting global providers).
-   **Key Properties/Methods:**
    -   `tracer`: Provides access to the configured OTel `Tracer` object (for
        creating spans). Returns `None` or a `NoOpTracer` if tracing is disabled
        or not initialized.
    -   `meter`: Provides access to the configured OTel `Meter` object (for
        creating metrics). Returns `None` or a `NoOpMeter` if metrics are
        disabled or not initialized.
    -   `logger`: Provides access to a standard Python `logging.Logger` that has
        been configured to automatically include trace context (trace ID, span
        ID) in log records.
    -   `propagator`: Provides access to the configured OTel `TextMapPropagator`
        (for context propagation).
    -   `start_as_current_span(...)`: A convenient wrapper around the OTel
        tracer's method to start a new trace span and make it the active one in
        the current context.
    -   `traced(...)`: A decorator to automatically wrap functions or methods in
        a trace span.
    -   `create_counter(...)`, `create_histogram(...)`,
        `create_up_down_counter(...)`: Wrappers to create different types of
        metric instruments using the configured meter.
    -   `log(...)`: A method to log messages using the trace-aware logger.
    -   `inject_context(...)`, `extract_context(...)`: Methods to handle context
        propagation for distributed tracing (adding/reading trace headers).
    -   `shutdown()`: Properly shuts down all underlying OTel components,
        ensuring buffered data is flushed (exported). Crucial to call this
        before your application exits.
    -   `reset()`: A class method primarily for testing, allowing the singleton
        instance to be shut down and reset.

### 3.3 Configuration: `TelemetrySettings` (`settings.py`)

This module uses **Pydantic**, a popular Python library for data validation and
settings management.

-   **Purpose:** To define the structure of all configuration options for the
    `cryostorm` library and load them, typically from environment variables.
-   **`BaseSettings`:** `TelemetrySettings` inherits from Pydantic's
    `BaseSettings`, which automatically attempts to load values from environment
    variables. It uses a `__` (double underscore) as the nested delimiter (e.g.,
    the environment variable `TRACING__EXPORTER_TYPE` maps to
    `settings.tracing.exporter_type`).
-   **`BaseConfig`:** A base Pydantic model used by all configuration
    sub-models. It enforces settings like `frozen=True` (making settings
    immutable after creation) and `extra="forbid"` (preventing unexpected
    configuration fields).
-   **Structure:** `TelemetrySettings` contains nested Pydantic models for
    different aspects:
    -   `ServiceInfo`: Basic info about your application (name, version,
        environment).
    -   `PropagationConfig`: Settings for context propagation.
    -   `TracingConfig`: Settings for distributed tracing.
    -   `MetricsConfig`: Settings for metrics collection.
    -   `LoggingConfig`: Settings for logging.
-   **Validation:** Pydantic automatically validates the types and constraints
    (e.g., `gt=0` for positive numbers, `ge=0.0, le=1.0` for rates) of the
    settings when loaded.
-   **Defaults:** Sensible default values are provided for most settings.
-   **`get_settings()`:** A cached function to load and return the
    `TelemetrySettings` instance, ensuring settings are loaded only once.

_(See Section 4 for a detailed breakdown of all configuration options)_

### 3.4 Building Components: The Builder and Factory Patterns

The library uses two common design patterns for creating objects:

1.  **Builder Pattern (`TelemetryBuilder` in `telemetry.py`):**

    -   **What:** A pattern used to construct complex objects step-by-step. The
        `TelemetryBuilder` takes the `TelemetrySettings` and has methods like
        `build_resource()`, `build_tracing()`, `build_metrics()`, etc. The final
        `build()` method assembles the complete `TelemetryComponents` object.
    -   **Why:** It separates the complex construction logic of the entire
        telemetry setup from the main `Telemetry` facade class. It makes the
        creation process more manageable and allows for potential flexibility in
        the future (e.g., omitting certain components).

2.  **Factory Pattern (`*Factory` classes in `resource.py`, `trace.py`, etc.):**
    -   **What:** A pattern where a dedicated "factory" object is responsible
        for creating instances of other objects. For example,
        `SpanExporterFactory` knows how to create different types of
        `SpanExporter` (Console, OTLP) based on configuration.
    -   **Why:**
        -   **Decoupling:** The code that _uses_ an exporter (e.g.,
            `SpanProcessorFactory`) doesn't need to know the specific details of
            _how_ each exporter type is created. It just asks the factory for
            one.
        -   **Centralized Creation Logic:** The logic for creating a specific
            type of object (like a `SpanExporter`) is contained within its
            corresponding factory.
        -   **Configuration:** Factories often take configuration parameters (or
            a settings object) to customize the object they create. The
            `from_settings` class methods are a convention in this library to
            create a factory instance directly from the main
            `TelemetrySettings`.

### 3.5 Component Interfaces: `TelemetryComponent` and `Factory` (`interface.py`)

This module defines abstract base classes (interfaces) that enforce a common
structure for components and factories.

-   **`TelemetryComponent` (Abstract Base Class - ABC):**

    -   **Purpose:** Defines the basic contract for major telemetry parts
        (Tracing, Metrics, Logging, Propagator).
    -   **Methods:**
        -   `setup()`: An abstract method that each component _must_ implement.
            This method contains the logic to initialize and configure the
            specific OpenTelemetry aspect (e.g., setting up the
            `TracerProvider`).
        -   `shutdown()`: A method (optional to override) for cleaning up
            resources when the application stops (e.g., flushing exporters).
    -   **Why:** Ensures all core components have a consistent way to be
        initialized and shut down by the main `Telemetry` class.

-   **`Factory[T]` (Generic Abstract Base Class - ABC):**
    -   **Purpose:** Defines the basic contract for all factory classes. The
        `[T]` makes it generic, meaning you specify the _type_ of object the
        factory creates (e.g., `Factory[SpanExporter]`).
    -   **Methods:**
        -   `create() -> T`: An abstract method that each factory _must_
            implement. This method contains the logic to instantiate and return
            an object of type `T`.
    -   **Why:** Enforces that all factories have a standard `create()` method,
        making them interchangeable from the perspective of the code that uses
        them.

### 3.6 Defining Constants: Enums (`constants.py`)

This module uses Python's `enum.StrEnum` to define sets of named constants.

-   **Purpose:** To provide clear, readable, and type-safe names for
    configuration options instead of using raw strings.
-   **Examples:**
    -   `EnvironmentType`: Defines valid environment names (`DEVELOPMENT`,
        `STAGING`, `PRODUCTION`).
    -   `ExporterType`: Defines valid exporter types (`CONSOLE`, `OTLP`,
        `IN_MEMORY`).
    -   `ProcessorType`: Defines valid processor types (`BATCH`, `SIMPLE`).
    -   `PropagatorType`: Defines valid context propagators (`TRACECONTEXT`,
        `BAGGAGE`).
    -   `SamplingStrategy`: Defines valid tracing sampling strategies.
    -   `LogLevel`: Defines standard logging levels.
-   **Why use Enums?**
    -   **Readability:** `ExporterType.OTLP` is clearer than `"otlp"`.
    -   **Type Safety:** Prevents typos. Using an incorrect string might pass
        silently, but using an undefined Enum member will raise an error.
    -   **Discoverability:** IDEs can easily show available options.
    -   **Maintainability:** If options change, you only need to update the Enum
        definition.

### 3.7 Representing Your Service: `Resource` (`resource.py`)

-   **`ResourceFactory`:**
    -   **Purpose:** Creates an OpenTelemetry `Resource` object.
    -   **What is a Resource?** A `Resource` is a collection of key-value pairs
        (attributes) that identify the entity producing telemetry data (i.e.,
        your application or service). These attributes are attached to _all_
        telemetry (traces, metrics, logs) originating from that entity.
    -   **Standard Attributes:** Common attributes include:
        -   `service.name`: The logical name of your service (e.g., `user-api`,
            `billing-service`). **Crucial for filtering/grouping in backends.**
        -   `service.version`: The version of your service (e.g., `1.2.3`,
            `git-commit-hash`).
        -   `deployment.environment`: The environment where the service is
            running (e.g., `development`, `production`).
    -   **Creation:** The factory takes service name, version, environment, and
        any additional custom attributes from `TelemetrySettings` and uses
        `Resource.create(...)` to build the object.

### 3.8 Handling Traces: `TracingComponent` (`trace.py`)

This module sets up the entire pipeline for distributed tracing.

-   **`SpanExporterFactory`:** Creates `SpanExporter` instances (Console, OTLP,
    In-Memory) based on `TracingConfig`. The OTLP exporter sends trace data to
    the Collector.
-   **`SpanProcessorFactory`:** Creates `SpanProcessor` instances (Batch,
    Simple) based on `TracingConfig`.
    -   `BatchSpanProcessor`: Collects spans in a queue and exports them in
        batches periodically or when the queue is full. **Recommended for
        production** for efficiency. Configured via `max_queue_size`,
        `schedule_delay_millis`, etc.
    -   `SimpleSpanProcessor`: Exports each span immediately as it ends. Easier
        for debugging but less efficient.
    -   The processor uses the exporter created by `SpanExporterFactory` to
        actually send the data.
-   **`TracingComponent`:**
    -   **Purpose:** Orchestrates the setup of the tracing pipeline using the
        factories and settings.
    -   **`setup()` Method:**
        1.  Creates a `Sampler` (using `SamplerFactory` from `sampler.py`) to
            decide which requests should be traced.
        2.  Creates a `SpanProcessor` (using `SpanProcessorFactory`).
        3.  Creates an OTel `TracerProvider`, configuring it with the
            `Resource`, `Sampler`, and `SpanProcessor`. The `TracerProvider` is
            the main entry point for the OTel tracing SDK.
        4.  Sets the created `TracerProvider` as the **global** provider using
            `trace.set_tracer_provider(...)`. This makes it available throughout
            your application.
        5.  Gets a `Tracer` instance from the global provider using
            `trace.get_tracer(...)`. This `Tracer` object is what's actually
            used to create spans (via `telemetry.tracer`).
    -   **`shutdown()` Method:** Calls `shutdown()` on the `TracerProvider`,
        which in turn shuts down the processor and exporter, ensuring buffered
        spans are flushed.

### 3.9 Handling Metrics: `MetricsComponent` (`metric.py`)

This module sets up the pipeline for collecting and exporting metrics.

-   **`MetricExporterFactory`:** Creates `MetricExporter` instances (Console,
    OTLP) based on `MetricsConfig`. The OTLP exporter sends metrics data to the
    Collector.
-   **`MetricReaderFactory`:** Creates `MetricReader` instances. The primary one
    used here is:
    -   `PeriodicExportingMetricReader`: Collects aggregated metric data at
        regular intervals (defined by `export_interval_millis`) and sends it to
        the configured `MetricExporter`. This is the standard way to export
        metrics in OTel.
-   **`MetricsComponent`:**
    -   **Purpose:** Orchestrates the setup of the metrics pipeline.
    -   **`setup()` Method:**
        1.  Creates a `MetricReader` (using `MetricReaderFactory`).
        2.  Creates an OTel `MeterProvider`, configuring it with the `Resource`
            and the `MetricReader`. The `MeterProvider` manages meters and the
            export process.
        3.  Sets the created `MeterProvider` as the **global** provider using
            `metrics.set_meter_provider(...)`.
        4.  Gets a `Meter` instance from the global provider using
            `metrics.get_meter(...)`. This `Meter` object is what's actually
            used to create metric instruments like counters and histograms (via
            `telemetry.meter`).
    -   **`shutdown()` Method:** Calls `shutdown()` on the `MeterProvider`,
        ensuring a final export of metrics occurs.

### 3.10 Handling Logs: `LoggingComponent` (`log.py`)

This module sets up the pipeline for exporting structured logs enriched with
trace context.

-   **`LogExporterFactory`:** Creates `LogExporter` instances (Console, OTLP)
    based on `LoggingConfig`. The OTLP exporter sends log data to the Collector.
-   **`LogProcessorFactory`:** Creates `LogRecordProcessor` instances (Batch,
    Simple) based on `LoggingConfig`.
    -   `BatchLogRecordProcessor`: Collects log records and exports them in
        batches. Configured via `max_queue_size`, `schedule_delay_millis`, etc.
    -   `SimpleLogRecordProcessor`: Exports each log record immediately.
-   **`LoggingComponent`:**
    -   **Purpose:** Configures Python's standard `logging` module to integrate
        with OpenTelemetry.
    -   **`setup()` Method:**
        1.  Creates a `LogRecordProcessor` (using `LogProcessorFactory`).
        2.  Creates an OTel `LoggerProvider`, configuring it with the `Resource`
            and the `LogRecordProcessor`.
        3.  Sets the created `LoggerProvider` as the provider for OTel logging
            using `set_logger_provider(...)`.
        4.  Uses `LoggingInstrumentor().instrument(...)`: This is the key step.
            It modifies the standard Python `logging` system:
            -   It automatically injects the current `trace_id` and `span_id`
                from the active trace context into log records.
            -   It can optionally set a logging format that includes these IDs.
        5.  Gets a standard Python `Logger` instance (`logging.getLogger(...)`)
            which is now "trace-aware". This logger is exposed via
            `telemetry.logger`.
        -   _Development Enhancement:_ If the environment is `DEVELOPMENT` and
            the primary exporter isn't already Console, it adds an _additional_
            `SimpleLogRecordProcessor` with a `ConsoleLogExporter` to ensure
            logs are always visible on the console during development.
    -   **`shutdown()` Method:** Calls `shutdown()` on the `LoggerProvider` and
        processors, and uninstruments the logging system.

### 3.11 Handling Context Propagation: `PropagatorComponent` (`propagator.py`)

This module configures how trace context is shared between services.

-   **`PropagatorFactory`:** Creates `TextMapPropagator` instances based on
    `PropagationConfig`.
    -   **What is a Propagator?** An object that knows how to inject (serialize)
        trace context into and extract (deserialize) trace context from a
        "carrier" (usually HTTP headers).
    -   **Supported Types (from `constants.PropagatorType`):**
        -   `TRACECONTEXT`: Implements the standard W3C TraceContext
            specification (uses `traceparent` and `tracestate` headers). **This
            is the recommended standard.**
        -   `BAGGAGE`: Implements the W3C Baggage specification (uses `baggage`
            header). Baggage allows propagating arbitrary key-value pairs along
            with the trace context.
    -   **`CompositePropagator`:** The factory typically creates a
        `CompositePropagator` that combines multiple individual propagators
        (e.g., both `TraceContextTextMapPropagator` and `W3CBaggagePropagator`
        by default). This allows compatibility with different systems.
-   **`PropagatorComponent`:**
    -   **Purpose:** Manages the propagator lifecycle.
    -   **`setup()` Method:**
        1.  Creates the configured `TextMapPropagator` using the factory.
        2.  Sets the created propagator as the **global** propagator using
            `opentelemetry.propagate.set_global_textmap(...)`. This makes it
            available for automatic instrumentation (like in web frameworks) and
            manual injection/extraction via `telemetry.propagator`.

### 3.12 Controlling Trace Volume: `Sampler` (`sampler.py`)

This module configures the tracing sampler.

-   **`SamplerFactory`:** Creates `Sampler` instances based on `TracingConfig`.
    -   **What is a Sampler?** An object that decides whether a given trace
        should be recorded and exported ("sampled") or ignored ("dropped").
        Sampling is crucial for managing the volume of trace data and reducing
        overhead in high-traffic systems.
    -   **Sampling Decision:** The decision is made when a _new trace_ is
        started (i.e., when the first span in a trace, the "root span," is
        created). The decision (sample or drop) is then propagated to downstream
        services via the trace context.
    -   **Supported Strategies (from `constants.SamplingStrategy`):**
        -   `ALWAYS_ON`: Samples every single trace. Useful for development or
            low-traffic environments.
        -   `ALWAYS_OFF`: Samples no traces. Useful for temporarily disabling
            tracing.
        -   `PARENT_BASED_ALWAYS_ON`: **Default strategy.** Respects the
            sampling decision of the parent span (if one exists via propagated
            context). If there's no parent, it _always_ samples. This ensures
            that if a trace was started upstream, the current service continues
            it, but new traces started in this service are always sampled.
        -   `PARENT_BASED_ALWAYS_OFF`: Respects the parent's decision. If no
            parent, it _never_ samples. Useful if you only want traces initiated
            by specific entry points.
        -   `TRACE_ID_RATIO`: Samples a fraction of traces based on the trace
            ID. For example, `sample_rate=0.1` samples approximately 10% of
            traces. This is a common strategy for production to control volume.
-   **Role in `TracingComponent`:** The `TracingComponent` uses this factory to
    create the sampler instance, which is then passed to the `TracerProvider`
    during setup.

---

## 4. Configuration In Detail (`settings.py`)

This library uses Pydantic for configuration, primarily loaded from environment
variables.

### 4.1 Loading Configuration

-   **Environment Variables:** Settings are loaded from environment variables.
    Nested settings use `__` (double underscore) as a separator. For example, to
    set the tracing exporter type, you would set the environment variable
    `TRACING__EXPORTER_TYPE=otlp`.
-   **`.env` Files:** The demo application uses `python-dotenv` to load
    environment variables from a `.env.local` file, which is a common practice
    for development.
-   **Pydantic `BaseSettings`:** The `TelemetrySettings` class inherits from
    `BaseSettings`, which handles the automatic loading and validation.
-   **Defaults:** If an environment variable is not set, the default value
    specified in the Pydantic model is used.
-   **Immutability:** Settings objects are "frozen" (`frozen=True`), meaning
    they cannot be changed after creation.

### 4.2 Main `TelemetrySettings`

This is the top-level container for all settings.

-   `service: ServiceInfo`: Defines information about the service being
    instrumented. (See below)
-   `schema_url: str`: (Default: `""`) Specifies the OpenTelemetry Schema URL.
    This URL identifies the version of the OpenTelemetry Semantic Conventions
    the telemetry data adheres to. Useful for ensuring compatibility and
    understanding across different tools.
-   `excluded_paths: list[str]`: (Default:
    `["/health", "/metrics", "/favicon.ico"]`) A list of URL paths that should
    be excluded from automatic tracing (e.g., by web framework instrumentation).
    Useful for ignoring noisy endpoints like health checks.
-   `propagation: PropagationConfig`: Configuration for context propagation.
    (See below)
-   `tracing: TracingConfig`: Configuration for distributed tracing. (See below)
-   `metrics: MetricsConfig`: Configuration for metrics. (See below)
-   `logging: LoggingConfig`: Configuration for logging. (See below)

### 4.3 `ServiceInfo`

Identifies the application producing telemetry. These become `Resource`
attributes.

-   `name: str`: (Default: `"unknown-service"`) The logical name of your service
    (e.g., `user-api`). **Required.**
-   `version: str`: (Default: `"0.1.0"`) The version of your service.
    **Required.**
-   `environment: EnvironmentType`: (Default: `EnvironmentType.DEVELOPMENT`) The
    deployment environment (`development`, `staging`, or `production`).
-   `additional_attributes: dict[str, Any]`: (Default: `{}`) A dictionary for
    any other custom attributes you want to attach to the resource (e.g.,
    `{"region": "us-east-1", "k8s.pod.name": "my-pod-xyz"}`).

### 4.4 `CollectorEndpoint`

Defines connection details for an OpenTelemetry Collector. Used within
`TracingConfig`, `MetricsConfig`, and `LoggingConfig`.

-   `host: str`: (Default: `"localhost"`) Hostname or IP address of the OTel
    Collector.
-   `port: int`: (Default: `4317`) Port number the Collector is listening on.
    **Note:** 4317 is the default for OTLP/gRPC, while 4318 is the default for
    OTLP/HTTP. Ensure this matches the receiver configuration in your Collector.
-   `protocol: Literal["http", "https"]`: (Default: `"http"`) Protocol to use.
    **Important:** Even for gRPC connections, OpenTelemetry SDKs often expect
    the base URL scheme, so `"http"` is typically correct unless you have TLS
    configured _between the application and the collector_ (which is separate
    from TLS between the collector and backends).
-   `url: str` (Computed Field): Automatically generates the full URL string
    like `http://localhost:4317`.

### 4.5 `ExportConfig`

Common settings for batch exporting behavior. Used within `TracingConfig` and
`LoggingConfig`.

-   `batch_size: int`: (Default: `512`) Maximum number of telemetry items (spans
    or logs) to include in a single export batch.
-   `schedule_delay_millis: int`: (Default: `5000`) Maximum time (in
    milliseconds) to wait before exporting an incomplete batch. A batch will be
    sent either when it's full (`batch_size`) or when this timer expires,
    whichever comes first.
-   `timeout_millis: int`: (Default: `30000`) Maximum time (in milliseconds) to
    wait for an export request to complete before timing out.

### 4.6 `PropagationConfig`

Settings for context propagation.

-   `enabled: bool`: (Default: `True`) Whether context propagation is enabled
    globally.
-   `propagator_types: list[PropagatorType]`: (Default:
    `[TRACECONTEXT, BAGGAGE]`) List of propagator types to use. The
    `CompositePropagator` will be configured to use all specified types.
    -   `TRACECONTEXT`: W3C Trace Context standard (uses `traceparent`,
        `tracestate` headers). **Recommended.**
    -   `BAGGAGE`: W3C Baggage standard (uses `baggage` header). Allows passing
        key-value pairs across service boundaries.
    -   `COMPOSITE`: This is used internally when multiple types are selected,
        not usually specified directly here.

### 4.7 `TracingConfig`

Settings specific to distributed tracing.

-   `enabled: bool`: (Default: `True`) Whether tracing is enabled.
-   `exporter_type: ExporterType`: (Default: `CONSOLE`) Type of exporter to use
    for spans (`CONSOLE`, `OTLP`, `IN_MEMORY`). Set to `OTLP` to send to the
    Collector.
-   `collector: CollectorEndpoint`: (Default: `host="localhost", port=4317`)
    Endpoint configuration if `exporter_type` is `OTLP`.
-   `processor_type: ProcessorType`: (Default: `BATCH`) Type of span processor
    (`BATCH`, `SIMPLE`). `BATCH` is recommended for performance.
-   `sampling_strategy: SamplingStrategy`: (Default: `PARENT_BASED_ALWAYS_ON`)
    How to decide which traces to sample. See Section 3.12 for details.
-   `sample_rate: float`: (Default: `1.0`) Sampling rate (between 0.0 and 1.0)
    used only if `sampling_strategy` is `TRACE_ID_RATIO`. `1.0` means sample
    everything, `0.1` means sample 10%.
-   `export_config: ExportConfig`: Batching and timeout settings for the span
    processor/exporter.
-   `additional_exporter_args: dict[str, Any]`: (Default: `{}`) Extra keyword
    arguments to pass directly to the chosen span exporter's constructor (e.g.,
    for specific TLS settings if needed, though often handled via endpoint URL).
-   `additional_processor_args: dict[str, Any]`: (Default: `{}`) Extra keyword
    arguments to pass directly to the chosen span processor's constructor.

### 4.8 `MetricsConfig`

Settings specific to metrics.

-   `enabled: bool`: (Default: `True`) Whether metrics collection is enabled.
-   `exporter_type: ExporterType`: (Default: `CONSOLE`) Type of exporter for
    metrics (`CONSOLE`, `OTLP`). Set to `OTLP` to send to the Collector.
-   `collector: CollectorEndpoint`: (Default: `host="localhost", port=4317`)
    Endpoint configuration if `exporter_type` is `OTLP`.
-   `export_interval_millis: int`: (Default: `60000`) How often (in
    milliseconds) the `PeriodicExportingMetricReader` should collect and export
    metrics.
-   `export_timeout_millis: int`: (Default: `30000`) Maximum time (in
    milliseconds) to wait for a metric export operation.
-   `additional_exporter_args: dict[str, Any]`: (Default: `{}`) Extra keyword
    arguments for the metric exporter constructor.

### 4.9 `LoggingConfig`

Settings specific to logging.

-   `enabled: bool`: (Default: `True`) Whether OTel log handling is enabled.
-   `processor_type: ProcessorType`: (Default: `SIMPLE`) Type of log processor
    (`BATCH`, `SIMPLE`). `SIMPLE` is often fine for logs unless volume is very
    high, but `BATCH` can be more efficient.
-   `exporter_type: ExporterType`: (Default: `CONSOLE`) Type of exporter for
    logs (`CONSOLE`, `OTLP`). Set to `OTLP` to send to the Collector.
-   `collector: CollectorEndpoint`: (Default: `host="localhost", port=4317`)
    Endpoint configuration if `exporter_type` is `OTLP`.
-   `level: LogLevel`: (Default: `INFO`) The _minimum_ log level that the
    configured logger will process (e.g., `INFO` means `INFO`, `WARNING`,
    `ERROR`, `CRITICAL` logs will be processed, but `DEBUG` logs will be
    ignored). This applies to the logger obtained via `telemetry.logger`.
-   `export_config: ExportConfig`: Default batching/timeout settings (can be
    overridden by specific settings below).
-   `schedule_delay_millis: int`: (Default: `5000`) Specific schedule delay for
    the `BatchLogRecordProcessor`. Overrides `export_config`.
-   `max_export_batch_size: int`: (Default: `512`) Specific batch size for the
    `BatchLogRecordProcessor`. Overrides `export_config`.
-   `export_timeout_millis: int`: (Default: `30000`) Specific timeout for log
    export. Overrides `export_config`.
-   `max_queue_size: int`: (Default: `512`) Maximum number of log records to
    buffer in the `BatchLogRecordProcessor`'s queue before potentially dropping
    logs if the exporter is slow.
-   `additional_processor_args: dict[str, Any]`: (Default: `{}`) Extra keyword
    arguments for the log processor constructor.
-   `additional_exporter_args: dict[str, Any]`: (Default: `{}`) Extra keyword
    arguments for the log exporter constructor.

---

## 5. How to Use `cryostorm` (Examples)

Here are basic examples showing how to use the `Telemetry` facade in your
application code.

### 5.1 Initialization

Typically done once when your application starts.

```python
import logging
from pathlib import Path
from dotenv import load_dotenv

from instrumentation.settings import TelemetrySettings
from instrumentation.telemetry import Telemetry

# --- 1. Load Configuration ---
# Load environment variables from a .env file (optional, good for development)
# Assumes .env.local is two directories up from the current file
# dotenv_path = Path(__file__).parents[1] / ".env.local"
# load_dotenv(override=False, dotenv_path=dotenv_path) # Set override=True to overwrite existing env vars

# Create the settings object - Pydantic loads from env vars automatically
try:
    settings = TelemetrySettings(
        # You can override specific settings programmatically if needed,
        # but usually rely on environment variables.
        # Example: service=ServiceInfo(name="my-cool-app", version="1.0")
    )
    print("Telemetry Settings Loaded:")
    print(settings.model_dump_json(indent=2)) # Pretty print the loaded settings
except Exception as e:
    print(f"Error loading Telemetry Settings: {e}")
    # Handle error appropriately, maybe exit or use default non-functional telemetry

# --- 2. Initialize Telemetry ---
# Create the singleton Telemetry instance using the loaded settings
try:
    telemetry = Telemetry.from_settings(settings)
    print("Telemetry initialized successfully.")
except Exception as e:
    print(f"FATAL: Failed to initialize telemetry: {e}")
    # Application might not function correctly without telemetry, decide how to handle this.
    # You could potentially fall back to basic logging.
    # For this example, we'll re-raise after logging.
    raise

# --- Application Lifecycle ---
# Your application code runs here...

# --- 3. Shutdown (Crucial!) ---
# Ensure shutdown is called before the application exits to flush buffered data
def shutdown_app():
    print("Shutting down application...")
    telemetry.shutdown()
    print("Telemetry shut down complete.")

# Example: Register shutdown hook (e.g., using atexit or framework signals)
import atexit
atexit.register(shutdown_app)

# Keep the example running briefly to simulate an application lifetime
import time
print("Application running...")
time.sleep(2)
print("Application exiting...")

# Note: In a real app (like FastAPI), initialization happens during startup lifespan,
# and shutdown happens during shutdown lifespan.
```

**Explanation:**

1.  **Load Configuration:** We first load environment variables (optionally from
    a `.env` file) and then create a `TelemetrySettings` object. Pydantic
    validates the settings.
2.  **Initialize Telemetry:** We pass the `settings` object to
    `Telemetry.from_settings()`. This creates the singleton instance and runs
    the internal `setup_all()` logic, configuring OTel.
3.  **Shutdown:** We define a `shutdown_app` function that calls
    `telemetry.shutdown()`. This is registered using `atexit` to ensure it's
    called when the script exits normally. **This step is vital** to ensure
    telemetry data buffered in memory (e.g., by batch processors) is sent before
    the application terminates.

### 5.2 Creating Traces (Spans)

Traces track the flow of a request. Each unit of work within a trace is a
"Span".

**Method 1: Using the `traced` decorator (Easiest)**

```python
# Assuming 'telemetry' instance is initialized as shown above

@telemetry.traced(span_name="my_custom_function_span") # Customize span name
def process_data(data: dict) -> dict:
    print(f"Processing data: {data}")
    # Simulate work
    time.sleep(0.1)
    result = {"processed": True, "input_keys": list(data.keys())}
    print("Processing complete.")
    return result

@telemetry.traced # Default span name will be 'module.function_name'
async def async_task(item_id: int):
    print(f"Starting async task for item {item_id}")
    # Add attributes to the current span automatically created by the decorator
    current_span = trace.get_current_span()
    current_span.set_attribute("item.id", item_id)
    current_span.add_event("Starting data fetch")

    # Simulate async work (e.g., database call)
    await asyncio.sleep(0.05)

    current_span.add_event("Data fetch complete")
    print(f"Async task for item {item_id} finished.")
    return {"status": "ok", "item_id": item_id}

# --- Usage ---
if telemetry.initialized: # Good practice to check if initialized
    processed_result = process_data({"user": "alice", "value": 123})
    # await async_task(42) # If running in an async context
else:
    print("Telemetry not initialized, skipping traced function calls.")

```

**Explanation:**

-   The `@telemetry.traced()` decorator automatically wraps the function call in
    an OTel span.
-   The span starts when the function is entered and ends when it exits (or
    raises an exception).
-   Duration is automatically calculated.
-   Exceptions are automatically recorded, and the span status is set to
    `ERROR`.
-   You can optionally provide a `span_name`. If omitted, it defaults to the
    function's qualified name (e.g., `__main__.process_data`).
-   You can add attributes (`kind`, `attributes`) to the decorator arguments.
-   Inside the decorated function, you can get the current span using
    `trace.get_current_span()` to add more attributes or events.

**Method 2: Using the `start_as_current_span` context manager (More Control)**

```python
# Assuming 'telemetry' instance is initialized

def handle_request(request_id: str):
    # Check if telemetry is enabled and get the tracer
    if not telemetry.initialized or not telemetry.tracer:
        print("Telemetry not available, processing request without tracing.")
        # Perform work without tracing...
        time.sleep(0.2)
        return {"status": "processed_untraced"}

    # Start a span using the context manager
    with telemetry.start_as_current_span(
        name="handle_web_request", # Descriptive name for the operation
        kind=trace.SpanKind.SERVER, # Indicates this span represents a server receiving a request
        attributes={ # Add initial key-value attributes
            "http.request.id": request_id,
            "http.method": "GET", # Example attribute
            "feature.flag.X": True, # Example attribute
        }
    ) as parent_span: # The context manager yields the created span object
        print(f"Started span for request: {request_id}")
        parent_span.add_event("Request validation started") # Record an event (timestamped log within the span)
        time.sleep(0.02)
        parent_span.add_event("Request validation complete")

        try:
            # Simulate doing work, potentially calling other traced functions
            # You can create nested spans for sub-operations
            with telemetry.start_as_current_span("database_query") as db_span:
                db_span.set_attribute("db.system", "postgresql")
                db_span.set_attribute("db.statement", "SELECT * FROM users WHERE id=?")
                print("  Executing DB query...")
                time.sleep(0.08) # Simulate DB call latency
                print("  DB query complete.")
                # db_span ends automatically here

            with telemetry.start_as_current_span("external_api_call") as api_span:
                api_span.set_attribute("http.url", "https://api.example.com/data")
                print("  Calling external API...")
                time.sleep(0.1) # Simulate API call latency
                print("  External API call complete.")
                # api_span ends automatically here

            # Set final status (optional, default is OK if no exception)
            parent_span.set_status(trace.Status(trace.StatusCode.OK))
            print(f"Finished span for request: {request_id}")
            return {"status": "processed_traced"}

        except Exception as e:
            print(f"Error during request {request_id}: {e}")
            # Record the exception on the span
            parent_span.record_exception(e)
            # Set the span status to Error
            parent_span.set_status(trace.Status(trace.StatusCode.ERROR, f"Request failed: {e}"))
            # Re-raise the exception if needed
            raise
        # parent_span ends automatically here, recording duration and status

# --- Usage ---
handle_request("req-123")
try:
    # Simulate a request that causes an error
    with telemetry.start_as_current_span("failing_operation") as span:
        span.set_attribute("attempt.number", 1)
        print("Running operation destined to fail...")
        time.sleep(0.05)
        raise ValueError("Something went wrong intentionally!")
except ValueError as e:
    print(f"Caught expected error: {e}")

```

**Explanation:**

-   The `with telemetry.start_as_current_span(...)` block creates a span and
    makes it the "current" span for its duration.
-   `name`: The name of the span (operation).
-   `kind`: The type of operation (e.g., `SERVER` for incoming requests,
    `CLIENT` for outgoing calls, `INTERNAL` for internal operations). Defaults
    to `INTERNAL`.
-   `attributes`: A dictionary of initial key-value metadata.
-   The `with` statement yields the created `Span` object, which you can use to:
    -   `set_attribute(key, value)`: Add more metadata.
    -   `add_event(name, attributes)`: Record a timestamped event within the
        span's lifetime.
    -   `record_exception(exception)`: Mark that an error occurred.
    -   `set_status(Status(...))`: Explicitly set the status (e.g., `OK`,
        `ERROR`). If an exception occurs within the `with` block and
        `set_status_on_exception` (default True) is used, the status is
        automatically set to `ERROR`.
-   The span automatically ends when the `with` block exits, calculating the
    duration.
-   Nested `with` blocks create child spans, forming the trace hierarchy.

### 5.3 Creating Metrics

Metrics measure numerical values over time.

```python
# Assuming 'telemetry' instance is initialized and metrics are enabled

# --- 1. Create Metric Instruments (usually done once at startup) ---
# Counter: Monotonically increasing value (e.g., total requests)
request_counter = telemetry.create_counter(
    name="app_requests_total",
    description="Total number of HTTP requests received",
    unit="requests" # Optional unit (follows UCUM standard ideally)
)

# Histogram: Records the distribution of values (e.g., request latency)
request_latency_hist = telemetry.create_histogram(
    name="app_request_latency_seconds",
    description="Distribution of application request latency",
    unit="s" # seconds
)

# UpDownCounter: Value can increase or decrease (e.g., active connections)
active_connections_counter = telemetry.create_up_down_counter(
    name="app_active_connections",
    description="Number of currently active connections",
    unit="connections"
)

# --- 2. Record Metric Values (done during application execution) ---

def simulate_web_request(endpoint: str, success: bool, duration_s: float):
    print(f"Simulating request to {endpoint} (Success: {success}, Duration: {duration_s:.3f}s)")

    # Define attributes (dimensions) for the metrics
    metric_attributes = {"http.endpoint": endpoint, "request.success": str(success)}

    # Increment the request counter
    request_counter.add(1, attributes=metric_attributes)

    # Record the duration in the histogram
    request_latency_hist.record(duration_s, attributes=metric_attributes)

def simulate_connection_change(change: int):
    server_id = "server-1" # Example attribute
    print(f"Simulating connection change: {change:+d} on {server_id}")
    active_connections_counter.add(change, attributes={"server.id": server_id})

# --- Usage ---
if telemetry.initialized and telemetry.meter: # Check if metrics are enabled
    simulate_web_request("/users", True, 0.055)
    simulate_web_request("/products", True, 0.120)
    simulate_web_request("/users", False, 0.530) # Simulate a slow, failed request

    simulate_connection_change(1) # Connection opened
    simulate_connection_change(1) # Another connection opened
    time.sleep(0.1)
    simulate_connection_change(-1) # Connection closed
else:
    print("Telemetry/Metrics not initialized, skipping metric recording.")

# Metrics are typically exported periodically in the background by the MetricReader.
# You don't explicitly call an 'export' function here.
```

**Explanation:**

1.  **Create Instruments:** You first create metric instruments using
    `telemetry.create_*` methods. This is usually done once at application
    startup.
    -   `create_counter`: For values that only increase (e.g., total requests,
        bytes sent).
    -   `create_histogram`: For recording the statistical distribution of values
        (e.g., latencies, request sizes). The backend (e.g., Prometheus) will
        typically calculate percentiles (p50, p90, p99) from this.
    -   `create_up_down_counter`: For values that can go up or down (e.g.,
        number of active users, items in a queue).
    -   `name`, `description`, `unit`: Provide metadata for the metric.
2.  **Record Values:** During your application's execution, you call methods on
    the created instruments:
    -   `counter.add(value, attributes)`: Increment the counter. `value` must be
        non-negative.
    -   `histogram.record(value, attributes)`: Record a measurement.
    -   `up_down_counter.add(value, attributes)`: Add the `value` (can be
        positive or negative).
    -   `attributes`: A dictionary of key-value pairs (dimensions) that allow
        you to slice and dice the metric data in your backend (e.g., view
        request count _per endpoint_). Attribute values should generally be
        strings, numbers, or booleans.

### 5.4 Generating Logs

Use the trace-aware logger provided by `telemetry.logger`.

```python
import logging

# Assuming 'telemetry' instance is initialized and logging is enabled

def process_user_data(user_id: str):
    # Start a span to provide context for logs
    with telemetry.start_as_current_span("process_user_data", attributes={"user.id": user_id}) as span:

        # Use the telemetry logger
        telemetry.log(
            level=logging.INFO,
            message=f"Starting data processing for user {user_id}",
            extra={"custom_field": "value1", "stage": "start"} # Add extra structured data
        )

        try:
            # Simulate work
            print(f"  Working on user {user_id}...")
            time.sleep(0.03)

            if user_id == "bad_user":
                raise ValueError("Invalid user ID encountered")

            telemetry.log(
                level=logging.DEBUG, # Debug messages might be filtered by config
                message="Intermediate step completed.",
                extra={"step": 5}
            )

            time.sleep(0.02)

            telemetry.log(
                level=logging.INFO,
                message="User data processing finished successfully.",
                extra={"stage": "end", "result": "success"}
            )
            span.set_attribute("processing.result", "success")

        except Exception as e:
            # Log the error - trace context is automatically included!
            telemetry.log(
                level=logging.ERROR,
                message=f"Failed to process data for user {user_id}: {e}",
                extra={"stage": "error"}
            )
            # The span context manager handles recording the exception on the span
            span.set_attribute("processing.result", "failure")
            # Decide whether to re-raise or handle the error
            # raise e

# --- Usage ---
if telemetry.initialized:
    process_user_data("user_123")
    process_user_data("user_456")
    try:
        process_user_data("bad_user")
    except ValueError:
        print("Caught expected processing error for bad_user.")
else:
    # Fallback to basic logging if telemetry isn't set up
    basic_logger = logging.getLogger(__name__)
    basic_logger.warning("Telemetry not initialized, using basic logger.")
    basic_logger.info("Processing user data (untraced)...")

```

**Explanation:**

-   Access the logger via `telemetry.logger`. This logger is configured by
    `LoggingComponent` to automatically include `trace_id` and `span_id` from
    the current span context.
-   Use standard Python `logging` levels (`logging.INFO`, `logging.ERROR`,
    etc.). The actual output depends on the level configured in `LoggingConfig`.
-   The `message` is the main log text.
-   The `extra` dictionary allows you to add arbitrary key-value pairs for
    structured logging. These fields will often be searchable in your logging
    backend (like Loki or Elasticsearch).
-   When logs are generated within an active span (created by
    `@telemetry.traced` or `start_as_current_span`), the trace context is
    automatically injected. This allows you to easily find all logs related to a
    specific request trace in your backend system.

### 5.5 Context Propagation (Manual)

When making requests to other services (e.g., HTTP calls), you need to inject
the current trace context into the request headers. When receiving requests, you
need to extract it.

_(Note: Many web framework instrumentations handle this automatically for
incoming requests and sometimes for outgoing requests using common libraries
like `requests` or `httpx`. This shows the manual process.)_

```python
import httpx # Example HTTP client library

# Assuming 'telemetry' instance is initialized and propagation is enabled

async def make_downstream_call(url: str, data: dict):
    # Assume we are already inside an active span (e.g., handling an incoming request)
    current_span = trace.get_current_span()
    print(f"Making downstream call within span: {current_span.get_span_context().span_id:x}")

    # 1. Inject Context into Headers
    headers = {}
    if telemetry.propagator:
        telemetry.inject_context(headers)
        print(f"  Injecting headers: {headers}") # Should contain 'traceparent', maybe 'tracestate', 'baggage'
    else:
        print("  Propagator not available, cannot inject context.")

    # 2. Make the HTTP Request with Injected Headers
    async with httpx.AsyncClient() as client:
        try:
            # Start a CLIENT span for the outgoing call
            with telemetry.start_as_current_span(
                "call_downstream_service",
                kind=trace.SpanKind.CLIENT,
                attributes={"http.url": url, "http.method": "POST"}
            ) as client_span:
                response = await client.post(url, json=data, headers=headers)
                client_span.set_attribute("http.status_code", response.status_code)
                print(f"  Downstream call to {url} returned status: {response.status_code}")
                response.raise_for_status() # Raise exception for bad status codes
                return response.json()
        except httpx.HTTPStatusError as e:
            print(f"  HTTP error calling {url}: {e}")
            # Exception is automatically recorded by start_as_current_span
            raise
        except Exception as e:
            print(f"  Error calling {url}: {e}")
            # Exception is automatically recorded by start_as_current_span
            raise

def handle_incoming_request(request_headers: dict):
    print(f"Handling incoming request with headers: {request_headers}")

    # 1. Extract Context from Headers
    extracted_context = None
    if telemetry.propagator:
        extracted_context = telemetry.extract_context(request_headers)
        print(f"  Extracted context: {extracted_context}") # This is an OTel Context object
    else:
        print("  Propagator not available, cannot extract context.")

    # 2. Start a SERVER Span using the Extracted Context
    # If extracted_context is None or empty, a new trace will be started.
    # Otherwise, this span becomes a child of the trace specified in the headers.
    with telemetry.start_as_current_span(
        "process_incoming_call",
        context=extracted_context, # Pass the extracted context here!
        kind=trace.SpanKind.SERVER,
        attributes={"service.entrypoint": "/incoming"}
    ) as server_span:
        trace_id = server_span.get_span_context().trace_id
        print(f"  Started server span with Trace ID: {trace_id:x}")
        # ... process the request ...
        time.sleep(0.06)
        print("  Finished processing incoming call.")

# --- Usage Simulation ---
# Simulate being inside a request handler span
with telemetry.start_as_current_span("main_request_handler") as main_span:
    # Simulate making an outgoing call
    # await make_downstream_call("http://example.com/api", {"key": "value"}) # If async

    # Simulate receiving a request with trace headers
    incoming_headers_with_trace = {
        "traceparent": f"00-{main_span.get_span_context().trace_id:032x}-{random.randint(0, 2**64-1):016x}-01",
        "Content-Type": "application/json"
        # Potentially also 'tracestate' and 'baggage' headers
    }
    handle_incoming_request(incoming_headers_with_trace)

    # Simulate receiving a request without trace headers (starts a new trace)
    incoming_headers_without_trace = {
        "Content-Type": "application/json"
    }
    handle_incoming_request(incoming_headers_without_trace)

```

**Explanation:**

-   **Injection (`inject_context`):** Before making an outgoing request (e.g.,
    HTTP, gRPC, message queue), create an empty dictionary (`headers = {}`) and
    call `telemetry.inject_context(headers)`. The configured propagator (e.g.,
    W3C TraceContext) will add the necessary headers (`traceparent`, etc.) to
    the dictionary. Include these headers in your outgoing request.
-   **Extraction (`extract_context`):** When receiving a request, get the
    incoming headers into a dictionary (`request_headers`). Call
    `telemetry.extract_context(request_headers)`. This returns an OTel `Context`
    object containing the trace information from the headers (or an empty
    context if no headers were found).
-   **Using Extracted Context:** Pass the `extracted_context` to the `context`
    argument of `telemetry.start_as_current_span(...)` when starting the span
    for handling the incoming request. This links the new span as a child of the
    trace initiated by the upstream service.

### 5.6 Shutdown

As shown in the Initialization example, always ensure `telemetry.shutdown()` is
called before your application exits.

```python
# At the very end of your application's lifecycle
print("Application shutting down...")
telemetry.shutdown()
print("Telemetry shutdown complete.")
```

---

## 6. Comprehensive Telemetry Flow Model (End-to-End)

This section details the journey of telemetry data from start to finish,
expanding on the original documentation and linking it explicitly to the
`cryostorm` library and the demo environment components.

### 6.1 Phase 0: Initialization and Configuration

-   **What:** Setting up the telemetry system before any data is generated.
-   **Where:** Application startup code.
-   **`cryostorm` Components:** `TelemetrySettings`, `Telemetry.from_settings`,
    `TelemetryBuilder`, `ResourceFactory`, `PropagatorFactory`,
    `TracingComponent`, `MetricsComponent`, `LoggingComponent`.
-   **Steps:**
    1.  **Load Configuration:** `TelemetrySettings` loads configuration from
        environment variables (or `.env.local` via `dotenv`). Pydantic validates
        the settings.
        ```python
        # settings.py loads env vars like SERVICE__NAME, TRACING__EXPORTER_TYPE etc.
        settings = TelemetrySettings()
        ```
    2.  **Instantiate Facade:** `Telemetry.from_settings(settings)` is called.
        This triggers the singleton creation.
    3.  **Build Components:** Inside `Telemetry.__init__` (called only once),
        `TelemetryBuilder(settings).build()` is invoked.
        -   `ResourceFactory.from_settings(settings).create()`: Creates the
            `Resource` object (service name, version, etc.).
        -   `PropagatorFactory.from_settings(settings).create()`: Creates the
            `CompositePropagator` (e.g., W3C TraceContext + Baggage).
        -   Factories for Exporters, Processors/Readers, and Samplers are
            created based on settings.
        -   `TracingComponent`, `MetricsComponent`, `LoggingComponent` instances
            are created, injecting their required factories and the `Resource`.
    4.  **Setup Components:** `TelemetryComponents.setup_all()` calls the
        `setup()` method on each component (`PropagatorComponent`,
        `TracingComponent`, `MetricsComponent`, `LoggingComponent`):
        -   `PropagatorComponent.setup()`: Sets the global text map propagator.
        -   `TracingComponent.setup()`: Creates and sets the global
            `TracerProvider` (with Resource, Sampler, Processor). Gets the
            `Tracer`.
        -   `MetricsComponent.setup()`: Creates and sets the global
            `MeterProvider` (with Resource, Reader). Gets the `Meter`.
        -   `LoggingComponent.setup()`: Creates the `LoggerProvider`,
            instruments the standard `logging` library, gets the trace-aware
            `Logger`.
-   **Result:** The `telemetry` object is ready, and the global OTel SDK
    providers are configured. The application can now generate telemetry.

### 6.2 Phase 1: Telemetry Generation (Inside Your App)

-   **What:** Creating traces, metrics, and logs during application runtime.
-   **Where:** Your application code (e.g., request handlers, background tasks).
-   **`cryostorm` Components:** `Telemetry` facade methods (`traced`,
    `start_as_current_span`, `create_counter`, `log`, etc.).
-   **Steps & Data:**
    1.  **Trace Generation:**
        -   Using `@telemetry.traced` or
            `with telemetry.start_as_current_span(...)`.
        -   **Data Created:** Span objects containing: Name, Kind (SERVER,
            CLIENT, INTERNAL), Start/End Timestamps (Duration), Attributes
            (key-value metadata), Events (timestamped annotations), Status
            (OK/ERROR), Parent Span ID (linking), Trace ID.
    2.  **Metric Recording:**
        -   Calling `add()` or `record()` on instruments created via
            `telemetry.create_*`.
        -   **Data Created:** Metric data points including: Value, Timestamp,
            Attributes (dimensions). These are aggregated _in memory_ by the SDK
            (e.g., counters are summed, histograms build distributions).
    3.  **Log Generation:**
        -   Calling `telemetry.log(level, message, extra)`.
        -   **Data Created:** Log records containing: Timestamp, Severity
            (Level), Body (Message), Attributes (`extra` dict), **Trace ID**,
            **Span ID** (automatically injected by the instrumented logger).
-   **In-Memory Accumulation:** This generated data isn't sent immediately.
    -   Completed Spans go to the `SpanProcessor`'s queue (e.g.,
        `BatchSpanProcessor`).
    -   Metric updates modify in-memory aggregators within the `MeterProvider`.
    -   Log records go to the `LogRecordProcessor`'s queue (e.g.,
        `BatchLogRecordProcessor`).
-   **Why Accumulate?** Batching improves performance by reducing the number of
    export operations (network calls).
-   **Risk:** If the application crashes before data is exported, buffered data
    can be lost.

### 6.3 Phase 2: Context Propagation (Linking Services)

-   **What:** Ensuring trace context (Trace ID, Span ID, sampling decision,
    baggage) is passed between different services when they communicate.
-   **Where:** Code that makes outgoing requests (e.g., HTTP client calls) and
    code that handles incoming requests (e.g., web framework middleware).
-   **`cryostorm` Components:** `telemetry.inject_context`,
    `telemetry.extract_context`, `PropagatorComponent`.
-   **Steps:**
    1.  **Injection (Outgoing Call):**
        -   Before making the call, create a carrier dictionary: `headers = {}`.
        -   Call `telemetry.inject_context(headers)`.
        -   The configured global propagator (e.g., `CompositePropagator` using
            W3C TraceContext and Baggage) adds headers like
            `traceparent: 00-trace_id-span_id-flags` and potentially
            `baggage: key1=value1` to the `headers` dictionary.
        -   Include these `headers` in the outgoing request (e.g.,
            `httpx.post(url, headers=headers)`).
    2.  **Extraction (Incoming Request):**
        -   When a request arrives, get the headers into a dictionary:
            `request_headers = dict(request.headers)`.
        -   Call `context = telemetry.extract_context(request_headers)`.
        -   The global propagator reads headers like `traceparent` and `baggage`
            and returns an OTel `Context` object containing the upstream trace
            information.
        -   Pass this `context` object when starting the new span for handling
            this request:
            `with telemetry.start_as_current_span(..., context=context, kind=SpanKind.SERVER):`.
            This links the new span as a child of the upstream span.
-   **Result:** Traces can span multiple services, providing an end-to-end view
    of requests.

### 6.4 Phase 3: SDK Processing and Export (Sending Data Out)

-   **What:** Preparing accumulated telemetry data and sending it from the
    application's OTel SDK to the configured destination (usually the OTel
    Collector).
-   **Where:** Background threads managed by the OTel SDK's Processors and
    Readers.
-   **`cryostorm` Components:** `SpanProcessor` (Batch/Simple), `MetricReader`
    (Periodic), `LogRecordProcessor` (Batch/Simple), `SpanExporter`
    (OTLP/Console), `MetricExporter` (OTLP/Console), `LogExporter`
    (OTLP/Console). Configuration from `TracingConfig`, `MetricsConfig`,
    `LoggingConfig`.
-   **Steps:**
    1.  **Batching Trigger:** Export happens when:
        -   A batch processor's queue reaches `batch_size` (spans/logs).
        -   A batch processor's `schedule_delay_millis` timer expires
            (spans/logs).
        -   A metric reader's `export_interval_millis` timer expires (metrics).
        -   `telemetry.shutdown()` is called (triggers a final flush/export).
    2.  **Data Transformation (Internal):**
        -   Spans: Finalized with duration, status.
        -   Metrics: Aggregated values (sums, counts, histogram buckets) are
            prepared for export.
        -   Logs: Formatted.
    3.  **Exporter Selection:** The processor/reader uses the specific exporter
        instance created during Phase 0 based on `exporter_type` settings (e.g.,
        `OTLPSpanExporter`).
    4.  **Serialization:** Data is converted into the format required by the
        exporter:
        -   **OTLP:** Serialized into Google Protocol Buffers (Protobuf), a
            binary format.
        -   **Console:** Formatted as human-readable text.
    5.  **Transmission:** The exporter sends the serialized data:
        -   **OTLP/gRPC:** Makes a gRPC network call to the Collector's endpoint
            (e.g., `http://localhost:4317`, configured via `collector.url`).
            Uses HTTP/2.
        -   **OTLP/HTTP:** Makes an HTTP POST request (with Protobuf payload) to
            the Collector's endpoint (e.g., `http://localhost:4318`).
        -   **Console:** Writes to standard output.
    6.  **Reliability:** Exporters typically handle connection timeouts
        (`timeout_millis`) and may have basic retry logic for transient network
        errors.

### 6.5 Phase 4: Collector Reception and Processing (Central Hub)

-   **What:** The OTel Collector receives data from the application SDK,
    processes it further, and routes it.
-   **Where:** The `otel-collector` service defined in
    `docker-compose-local.yml`. Configuration in `collector-config.yaml`.
-   **Components:** Collector `receivers`, `processors`, `service`/`pipelines`.
-   **Steps:**
    1.  **Reception:** The configured `receivers` listen for incoming data.
        -   `otlp` receiver listens on ports `4317` (gRPC) and `4318` (HTTP) as
            defined in `collector-config.yaml`.
        -   It accepts connections, parses the protocol, deserializes the
            Protobuf messages, and converts them into the Collector's internal
            data format.
    2.  **Pipeline Routing:** The `service.pipelines` section directs data based
        on type (traces, metrics, logs) to the appropriate pipeline.
        -   Example: Incoming OTLP traces go to the `traces` pipeline.
    3.  **Processing:** Data flows through the `processors` listed in its
        pipeline (e.g., `[batch]` in the example config).
        -   `batch`: Can perform additional batching for efficiency before
            exporting to backends.
        -   `memory_limiter` (Optional): Prevents the collector from crashing
            due to excessive memory usage under high load by dropping data if
            limits are exceeded.
        -   `resource` (Optional): Can add/modify resource attributes (e.g., add
            Kubernetes metadata).
        -   Other processors exist for filtering, sampling (tail-based),
            attribute manipulation, etc.
-   **Result:** Telemetry data is potentially transformed, enriched, and
    batched, ready for export to specialized backends.

### 6.6 Phase 5: Collector Export (To Backends)

-   **What:** The OTel Collector sends the processed data to the final backend
    systems.
-   **Where:** The `otel-collector` service. Configuration in
    `collector-config.yaml`.
-   **Components:** Collector `exporters`, `service`/`pipelines`.
-   **Steps:**
    1.  **Exporter Selection:** The pipeline routes data to the configured
        `exporters`.
        -   `traces` pipeline -> `otlp` exporter (sending to Jaeger), `debug`
            exporter.
        -   `metrics` pipeline -> `prometheus` exporter, `debug` exporter.
        -   `logs` pipeline -> `debug` exporter.
    2.  **Protocol/Format:** Each exporter uses the protocol and format required
        by its destination:
        -   `otlp` exporter (to Jaeger): Sends OTLP/gRPC to `jaeger:4317` (as
            configured in `exporters.otlp.endpoint`). The hostname `jaeger`
            resolves to the Jaeger container's IP address because they are on
            the same `otel-demo` Docker network. `tls.insecure: true` means TLS
            is not used for this connection _within_ the Docker network.
        -   `prometheus` exporter: Doesn't actively push. It opens an HTTP
            endpoint (`0.0.0.0:8889` as configured) and serves metrics in the
            Prometheus text format when Prometheus scrapes it.
            `resource_to_telemetry_conversion: enabled: true` helps convert OTel
            resource attributes (like `service.name`) into Prometheus labels.
        -   `debug` exporter: Writes detailed telemetry data to the Collector's
            standard output (useful for troubleshooting).
    3.  **Interaction Model:**
        -   Traces (to Jaeger): **Push** model. Collector actively sends data.
        -   Metrics (to Prometheus): **Pull** model. Collector exposes an
            endpoint; Prometheus scrapes it.
        -   Logs (to Debug): **Push** model (to console).
    4.  **Reliability:** Collector exporters typically have more robust retry
        mechanisms (e.g., exponential backoff) and potentially queuing
        capabilities (persistent or in-memory) to handle temporary backend
        unavailability.

### 6.7 Phase 6: Backend Storage and Indexing (Saving Data)

-   **What:** The specialized backend systems receive data from the Collector
    and store it efficiently for later querying.
-   **Where:** `jaeger` and `prometheus` services in `docker-compose-local.yml`.
-   **Components:** Jaeger storage engine, Prometheus TSDB (Time-Series
    Database).
-   **Steps:**
    1.  **Jaeger (Traces):**
        -   Receives OTLP trace data from the Collector on port 4317.
        -   **Storage:** In the demo setup (`SPAN_STORAGE_TYPE=memory`), traces
            are stored **only in RAM** and are lost when Jaeger restarts.
            Production setups typically use persistent storage like
            Elasticsearch or Cassandra, configured via environment variables.
        -   **Indexing:** Indexes spans by Trace ID, service name, operation
            name, time, and attributes (tags) to allow fast searching via the UI
            or API.
    2.  **Prometheus (Metrics):**
        -   **Scraping:** Periodically (defined in `prometheus.yml`, typically
            15-60s) sends an HTTP GET request to the Collector's Prometheus
            exporter endpoint (`otel-collector:8889`).
        -   **Storage:** Parses the text-format response and stores the metrics
            in its local **Time-Series Database (TSDB)** on disk (inside the
            container, potentially mapped to a host volume for persistence if
            configured).
        -   **Data Model:** Stores data as
            `metric_name{label1="value1", label2="value2"} timestamp value`.
        -   **Indexing:** Efficiently indexes metrics by name and labels.
        -   **Retention:** Data is typically kept for a configurable period
            (e.g., 15 days) before being deleted.
    3.  **Loki (Logs - Future):** Would receive logs (likely via OTLP or a
        specific Loki exporter in the Collector), index them based on labels
        (like `service.name`, `level`), and store the log content compressed.

### 6.8 Phase 7: Query and Visualization (Using Data)

-   **What:** Users or other systems accessing the stored telemetry data for
    analysis, dashboarding, and alerting.
-   **Where:** Jaeger UI, Prometheus UI, Grafana (if added), APIs.
-   **Components:** Backend query engines and UIs.
-   **Steps:**
    1.  **Jaeger UI:**
        -   Accessible via the mapped port (default `16686` on the host, e.g.,
            `http://localhost:16686`).
        -   Allows searching for traces by service, operation, tags
            (attributes), duration, time range.
        -   Visualizes trace timelines (Gantt charts) showing parent-child
            relationships and durations.
    2.  **Prometheus UI / PromQL:**
        -   Accessible via the mapped port (default `9090` on the host, e.g.,
            `http://localhost:9090`).
        -   Provides an interface to write **PromQL** queries to select,
            aggregate, and transform metrics over time (e.g., calculate rates,
            sums, averages, percentiles).
        -   Basic graphing capabilities.
        -   Used to define alerting rules.
    3.  **Grafana (If Added):**
        -   Connects to Jaeger and Prometheus (and potentially Loki) as data
            sources.
        -   Allows building sophisticated dashboards combining traces, metrics,
            and logs.
        -   Provides advanced visualization options and alerting features.
    4.  **Correlation:** A key benefit is correlating different signals. For
        example:
        -   Clicking on a point in a Grafana metric graph might provide a link
            to relevant traces in Jaeger from that time.
        -   Viewing a trace in Jaeger might allow you to jump to related logs
            using the Trace ID.

---

## 7. Understanding the Demo Environment (`docker-compose-local.yml`)

This file uses Docker Compose to define and run the multi-container application
environment needed for development and demonstration.

### 7.1 What is Docker Compose?

Docker Compose is a tool for defining and running multi-container Docker
applications. You use a YAML file (like `docker-compose-local.yml`) to configure
your application's services, networks, and volumes. Then, with a single command
(`docker compose up`), you can create and start all the services from your
configuration.

### 7.2 Service: `otel-collector`

-   **Purpose:** Runs the OpenTelemetry Collector.
-   **`image`:**
    `otel/opentelemetry-collector-contrib:${OTEL_COLLECTOR_CONTRIB_VERSION:-0.123.0}`
    -   Uses the official "contrib" image, which includes many extra components
        not in the base `otel/opentelemetry-collector` image.
    -   Uses an environment variable `OTEL_COLLECTOR_CONTRIB_VERSION` for the
        version, defaulting to `0.123.0`. This allows easy version updates via
        the `.env.local` file.
-   **`container_name`:** `${OTEL_COLLECTOR_CONTAINER_NAME:-otel-collector}`
    -   Sets a predictable name for the container, defaulting to
        `otel-collector`.
-   **`command`:**
    `["--config=${OTEL_CONFIG_CONTAINER_PATH:-/etc/otel-collector-config.yaml}"]`
    -   Tells the collector process inside the container which configuration
        file to load. The path `/etc/otel-collector-config.yaml` is the location
        _inside_ the container.
-   **`volumes`:**
    `- ${OTEL_CONFIG_HOST_PATH:-./config/collector-config.yaml}:/${OTEL_CONFIG_CONTAINER_PATH:-/etc/otel-collector-config.yaml}`
    -   **Crucial:** Mounts the local `config/collector-config.yaml` file (on
        your host machine) into the container at
        `/etc/otel-collector-config.yaml`. This allows you to edit the collector
        configuration locally, and the running collector will see the changes
        (though a restart via `docker compose restart otel-collector` is usually
        needed to apply them).
-   **`ports`:** Maps ports from your host machine to the container:
    -   `4317:4317`: Exposes the OTLP/gRPC receiver port. Your application
        (`web` service or local scripts) sends data here.
    -   `4318:4318`: Exposes the OTLP/HTTP receiver port.
    -   `8888:8888`: Potentially exposes the collector's _internal_ Prometheus
        metrics (if configured in collector config's `telemetry` section).
    -   `8889:8889`: Exposes the `prometheus` exporter endpoint. The
        `prometheus` service scrapes this port.
    -   `13133:13133`: Exposes the `health_check` extension endpoint.
-   **`depends_on`:** `jaeger`, `prometheus`
    -   Ensures Docker Compose starts Jaeger and Prometheus _before_ starting
        the collector. This doesn't guarantee they are _ready_, just started.
-   **`networks`:** `otel-demo`
    -   Connects the collector to the custom Docker network, allowing it to
        communicate with other services (like `jaeger`) using their service
        names.

### 7.3 Service: `jaeger`

-   **Purpose:** Runs the Jaeger distributed tracing backend (UI, query,
    collector, storage - all-in-one image).
-   **`image`:** `jaegertracing/jaeger:${JAEGER_VERSION:-2.2.0}`
    -   Uses the official Jaeger all-in-one image, version controlled by
        `JAEGER_VERSION` env var.
-   **`container_name`:** `${JAEGER_CONTAINER_NAME:-jaeger}`
    -   Sets a predictable container name.
-   **`ports`:**
    -   `16686:16686`: Exposes the Jaeger Web UI port. You access this in your
        browser (`http://localhost:16686`).
    -   Other ports (like 4317, 4318 for OTLP) are commented out because the
        `otel-collector` is responsible for receiving data from applications and
        forwarding it to Jaeger _internally_ over the Docker network
        (`jaeger:4317`).
-   **`restart`:** `unless-stopped`
    -   Automatically restarts the container if it crashes or the Docker daemon
        restarts, unless explicitly stopped. Good for development stability.
-   **`environment`:**
    -   `SPAN_STORAGE_TYPE=memory`: **Important:** Configures Jaeger to store
        trace data **in memory only**. Data is lost on restart. Suitable only
        for development/demo. Production requires persistent storage like
        `elasticsearch` or `cassandra`.
    -   `COLLECTOR_OTLP_ENABLED=true`: (Commented out, likely default now)
        Explicitly enables the OTLP receiver within Jaeger (though we send via
        the OTel Collector here).
-   **`deploy.resources.limits`:**
    -   `cpus: '1'`: Limits the container to 1 CPU core.
    -   `memory: 1G`: Limits the container to 1 GB of RAM. Prevents Jaeger from
        consuming excessive host resources.
-   **`networks`:** `otel-demo`
    -   Connects Jaeger to the network so the `otel-collector` can send data to
        it using the hostname `jaeger`.

### 7.4 Service: `prometheus`

-   **Purpose:** Runs the Prometheus time-series database and monitoring system.
-   **`image`:** `prom/prometheus:${PROMETHEUS_VERSION:-v2.53.4}`
    -   Uses the official Prometheus image, version controlled by
        `PROMETHEUS_VERSION` env var.
-   **`container_name`:** `prometheus`
    -   Sets a fixed container name.
-   **`command`:** Specifies command-line flags for Prometheus:
    -   `--config.file=/etc/prometheus/prometheus.yml`: Tells Prometheus where
        to find its config file _inside_ the container.
    -   `--web.enable-lifecycle`: Enables API endpoints for reloading config
        (`/-/reload`) without restarting.
    -   `--web.console.libraries`, `--web.console.templates`: Paths for legacy
        console templates.
-   **`volumes`:** `- ./config/prometheus.yml:/etc/prometheus/prometheus.yml`
    -   Mounts the local `config/prometheus.yml` file into the container. Allows
        local editing of Prometheus configuration (scrape targets, rules).
        Changes require a reload (`curl -X POST http://localhost:9090/-/reload`)
        or container restart.
-   **`ports`:**
    -   `9090:9090`: Exposes the Prometheus Web UI and API port. You access this
        in your browser (`http://localhost:9090`).
-   **`networks`:** `otel-demo`
    -   Connects Prometheus to the network so it can scrape the `otel-collector`
        using the target address `otel-collector:8889` (defined in
        `prometheus.yml`).

### 7.5 Service: `web` (Demo Application)

-   **Purpose:** Runs the example FastAPI application (`demo/llm_app.py`) that
    uses the `cryostorm` library.
-   **`build`:**
    -   `context: .`: Specifies that the build context (files available during
        image build) is the current directory (where `docker-compose-local.yml`
        resides).
    -   `dockerfile: Dockerfile.local`: Tells Docker Compose to build an image
        using the instructions in `Dockerfile.local` instead of pulling a
        pre-built image. This Dockerfile would typically copy the application
        code and install dependencies (including `cryostorm`).
-   **`container_name`:** `web`
    -   Sets a fixed container name.
-   **`ports`:**
    -   `8000:8000`: Exposes the FastAPI application's port. You can interact
        with the demo API via `http://localhost:8000`.
-   **`depends_on`:** `otel-collector`
    -   Ensures the collector is started before the web application. This
        increases the likelihood that the collector is ready to receive
        telemetry when the app starts sending it.
-   **`networks`:** `otel-demo`
    -   Connects the web app to the network so it can send telemetry data to the
        collector using the hostname `otel-collector` (e.g., connecting to
        `otel-collector:4317`).

### 7.6 Network: `otel-demo`

-   **`networks`:** Defines the custom Docker networks used by the services.
-   **`otel-demo`:** Defines a network named `otel-demo`.
-   **`driver: bridge`:** Uses the standard Docker bridge network driver. This
    creates a private, isolated network for the containers attached to it.
    Docker provides automatic DNS resolution within this network, allowing
    containers to reach each other using their service names (e.g., `web` can
    reach `otel-collector`, `otel-collector` can reach `jaeger`).

### 7.7 Volumes

-   **`volumes`:** Defines named volumes for persistent storage (though only
    `elasticsearch-data` is defined and not currently used by Jaeger in this
    config).
-   **`elasticsearch-data`:** Defines a named volume. If Jaeger were configured
    to use Elasticsearch for storage, this volume could be mounted to the
    Elasticsearch container to persist its data across container restarts.
-   **`grafana-storage`:** (Commented out) Would define a volume for Grafana's
    internal database if Grafana were included.

---

## 8. Understanding the Collector Configuration (`collector-config.yaml`)

This file tells the `otel-collector` service how to behave: what data to
receive, how to process it, and where to send it.

### 8.1 `receivers`

Defines how the Collector accepts incoming telemetry data.

-   **`otlp`:** Defines a receiver named `otlp`.
    -   **`protocols`:** Specifies the protocols the `otlp` receiver should use:
        -   **`grpc`:** Enables the OTLP over gRPC protocol.
            -   `endpoint: 0.0.0.0:4317`: Tells the receiver to listen on all
                network interfaces (`0.0.0.0`) inside the container on port
                `4317`. This is the standard port for OTLP/gRPC. Your
                application SDK (configured via `cryostorm`) sends data here.
        -   **`http`:** Enables the OTLP over HTTP protocol.
            -   `endpoint: 0.0.0.0:4318`: Tells the receiver to listen on port
                `4318`. This is the standard port for OTLP/HTTP.

### 8.2 `processors`

Defines components that process telemetry data as it flows through the
Collector. Processors are chained together in pipelines.

-   **`batch`:** Defines a batch processor.
    -   **Purpose:** Groups telemetry data (spans, metrics, logs) into batches
        before sending them to exporters. This improves efficiency and reduces
        load on backend systems. It can provide secondary batching even if the
        SDK already batches. Default settings are used if not specified.
-   **`memory_limiter`:** (Commented out)
    -   **Purpose:** Protects the Collector from running out of memory under
        high load.
    -   `check_interval`: How often to check memory usage.
    -   `limit_mib`: Memory limit in Mebibytes. If exceeded, the collector
        starts refusing data.
    -   `spike_limit_mib`: A higher limit to accommodate temporary spikes.
-   **`resource`:** (Commented out)
    -   **Purpose:** Modifies resource attributes attached to telemetry. Can be
        used to add common attributes (like region) or override existing ones.

### 8.3 `exporters`

Defines how the Collector sends telemetry data to final destinations (backends).

-   **`debug`:** Defines an exporter that prints telemetry data to the
    Collector's console output.
    -   **Purpose:** Extremely useful for debugging and verifying that data is
        flowing through the collector correctly.
    -   `verbosity: detailed`: Prints more information.
    -   `sampling_initial`, `sampling_thereafter`: Limits the rate of output to
        avoid flooding the console.
-   **`prometheus`:** Defines an exporter that makes metrics available for a
    Prometheus server to scrape.
    -   **Purpose:** Converts OTel metrics into the Prometheus exposition
        format.
    -   `endpoint: 0.0.0.0:8889`: Specifies the address and port where this
        exporter will listen for scrape requests from Prometheus. The
        `prometheus` service in `docker-compose-local.yml` is configured (in its
        own `prometheus.yml`) to scrape this target (`otel-collector:8889`).
    -   `namespace: otel_demo`: Adds a prefix (`otel_demo_`) to all metric names
        exposed via this exporter. Helps avoid naming collisions.
    -   `send_timestamps: true`: Includes timestamps with the exported metrics.
    -   `resource_to_telemetry_conversion: enabled: true`: Converts OTel
        resource attributes (like `service.name`) into Prometheus labels on the
        metrics.
-   **`otlp`:** Defines an exporter that sends data using the OTLP protocol
    (typically to another Collector or a backend like Jaeger that supports
    OTLP).
    -   **Purpose:** Used here to send trace data to the Jaeger backend.
    -   `endpoint: jaeger:4317`: The address of the destination. `jaeger` is the
        service name of the Jaeger container (resolved via Docker networking),
        and `4317` is the port where Jaeger's OTLP/gRPC receiver listens.
    -   `tls: insecure: true`: Disables TLS encryption for this connection. This
        is acceptable _within_ the private Docker network but should be `false`
        (or configured properly with certificates) if sending data over
        untrusted networks.

### 8.4 `extensions`

Defines additional capabilities for the Collector, not directly part of the data
pipeline.

-   **`health_check`:** Enables an HTTP endpoint that reports the Collector's
    health status.
    -   `endpoint: 0.0.0.0:13133`: Makes the health check available on port
        `13133`. Useful for monitoring or load balancers.
-   **`pprof`:** Enables an endpoint for Go performance profiling (`pprof`).
    Useful for diagnosing Collector performance issues.
    -   `endpoint: 0.0.0.0:1777`: Exposes the `pprof` endpoint.
-   **`zpages`:** Enables diagnostic web pages (`zPages`) for inspecting
    internal Collector state.
    -   `endpoint: 0.0.0.0:55679`: Exposes the `zPages` endpoint.

### 8.5 `service` (Pipelines)

Defines how telemetry data flows through the Collector by connecting receivers,
processors, and exporters.

-   **`extensions: [health_check, pprof, zpages]`:** Enables the configured
    extensions globally for the service.
-   **`pipelines`:** Defines data processing pipelines for each signal type
    (traces, metrics, logs).
    -   **`traces`:** Defines a pipeline for trace data.
        -   `receivers: [otlp]`: Receives traces from the `otlp` receiver.
        -   `processors: [batch]`: Processes the traces using the `batch`
            processor.
        -   `exporters: [otlp, debug]`: Sends the processed traces to _both_ the
            `otlp` exporter (to Jaeger) and the `debug` exporter (to console).
    -   **`metrics`:** Defines a pipeline for metric data.
        -   `receivers: [otlp]`: Receives metrics from the `otlp` receiver.
        -   `processors: [batch]`: Processes metrics using the `batch`
            processor.
        -   `exporters: [prometheus, debug]`: Sends metrics to the `prometheus`
            exporter (for scraping) and the `debug` exporter.
    -   **`logs`:** Defines a pipeline for log data.
        -   `receivers: [otlp]`: Receives logs from the `otlp` receiver.
        -   `processors: [batch]`: Processes logs using the `batch` processor.
        -   `exporters: [debug]`: Sends logs only to the `debug` exporter
            (console output). _Note: To send logs to Loki, you would add a Loki
            exporter configuration and add its name to this list._

---

## 9. Resilience and Lifecycle Management

Ensuring the telemetry system is reliable and behaves correctly during startup
and shutdown.

### 9.1 Fault Tolerance

Mechanisms to handle failures gracefully.

-   **Data Buffering:**
    -   **SDK:** `BatchSpanProcessor` and `BatchLogRecordProcessor` buffer data
        in memory queues (`max_queue_size`).
    -   **Collector:** The `batch` processor also buffers in memory. Optional
        persistent queue processors exist for the Collector to buffer to disk if
        backends are down for extended periods (not configured in this demo).
    -   **Impact:** Buffering helps handle short network blips or brief backend
        unavailability but risks data loss if the component holding the buffer
        crashes.
-   **Retry Mechanisms:**
    -   **SDK Exporters:** OTLP exporters have basic retry logic for transient
        network errors.
    -   **Collector Exporters:** Typically implement more robust exponential
        backoff retry strategies when sending data to backends fails.
-   **Circuit Breaking:** (Primarily in Collector)
    -   `memory_limiter` processor acts as a form of circuit breaking based on
        resource usage.
    -   Exporters might implement circuit breaking if a backend consistently
        fails, preventing hammering a dead service.
-   **Degraded Operations:**
    -   If telemetry initialization fails, `cryostorm` properties (`tracer`,
        `meter`) might return No-Op implementations, allowing the application to
        run but without generating telemetry.
    -   Sampling (`SamplerFactory`) reduces data volume under normal operation,
        which inherently limits impact during high load. Collector processors
        can implement further load shedding.

### 9.2 Lifecycle Management

Ensuring proper startup and shutdown.

-   **Initialization Sequence (`Telemetry._initialize`):**
    1.  Loads settings (`TelemetrySettings`).
    2.  Builds components via `TelemetryBuilder` (Resource -> Propagator ->
        Tracing -> Metrics -> Logging).
    3.  Calls `setup()` on each component in order, configuring global OTel
        providers.
    -   **Importance:** Correct order ensures dependencies are met (e.g.,
        Resource exists before Tracing/Metrics/Logging components are built).
-   **Graceful Shutdown (`Telemetry.shutdown`,
    `TelemetryComponents.shutdown_all`):**
    1.  Calls `shutdown()` on components, typically in reverse order of setup
        (`Tracing`, `Metrics`, `Logging`, `Propagator`).
    2.  Each component's `shutdown()` method calls `shutdown()` on its
        underlying OTel provider (`TracerProvider`, `MeterProvider`,
        `LoggerProvider`).
    3.  Provider shutdown triggers a **final flush** operation on associated
        processors/readers/exporters, attempting to send any buffered data.
    -   **Importance:** Crucial for preventing data loss. Must be called before
        application exit.
-   **Resource Cleanup:** Shutdown methods release resources like network
    connections held by exporters and terminate background threads used by batch
    processors or periodic readers.

### 9.3 Performance Considerations

Minimizing the impact of telemetry collection on application performance.

-   **CPU Overhead:**
    -   Creating spans and recording metrics/logs has some CPU cost.
    -   Sampling (`SamplerFactory`) significantly reduces the number of traces
        processed and exported.
    -   Batching (SDK and Collector `batch` processors) amortizes the cost of
        serialization and export over many items.
    -   Using efficient protocols like OTLP/gRPC (binary Protobuf) is generally
        less CPU-intensive than text-based formats.
-   **Memory Usage:**
    -   In-memory buffers (batch processors, metric aggregators) consume RAM.
    -   Configuration (`max_queue_size`, `batch_size`) limits buffer sizes.
    -   Periodic flushing/exporting prevents unbounded buffer growth.
    -   Collector `memory_limiter` provides a safety net.
-   **Network Bandwidth:**
    -   Exporting telemetry consumes network bandwidth.
    -   Batching reduces the number of requests and protocol overhead.
    -   Binary protocols (OTLP/gRPC) are typically more compact than text/JSON
        formats.
    -   Sampling drastically reduces the volume of trace data sent.
    -   Filtering attributes (not explicitly shown, but possible in Collector)
        can reduce data size.
-   **Storage Efficiency (Backends):**
    -   Backends use compression (e.g., Prometheus TSDB, Jaeger with
        Elasticsearch/Cassandra).
    -   Sampling reduces the amount of data needing storage.
    -   Data retention policies in backends prevent indefinite storage growth.

---

## 10. Extensions and Customizations

While `cryostorm` aims for simplicity, the underlying OpenTelemetry SDK is
highly extensible.

### 10.1 Custom Exporters

-   **How:** You can implement the `SpanExporter`, `MetricExporter`, or
    `LogExporter` interface from the OTel SDK to send data to custom backends or
    formats not supported out-of-the-box.
-   **Integration:** You would need to modify the corresponding factory
    (`SpanExporterFactory`, etc.) in `cryostorm` to recognize a new
    `ExporterType` and instantiate your custom exporter.

### 10.2 Custom Processors

-   **How:** Implement the `SpanProcessor` or `LogRecordProcessor` interface to
    add custom logic to the telemetry pipeline _within the SDK_. Examples:
    automatically adding specific attributes to all spans, filtering sensitive
    data, or creating custom metrics based on span data.
-   **Integration:** Modify the relevant factory (`SpanProcessorFactory`,
    `LogProcessorFactory`) to create and potentially chain your custom
    processor.

### 10.3 Custom Samplers

-   **How:** Implement the `Sampler` interface to create complex sampling
    decisions based on trace attributes (e.g., sample all traces for a specific
    user ID, sample errors at a higher rate).
-   **Integration:** Modify `SamplerFactory` to recognize a new
    `SamplingStrategy` and instantiate your custom sampler.

### 10.4 Backend Integrations

-   The primary way to integrate with different backends is via the
    **OpenTelemetry Collector**. The Collector has a wide range of built-in and
    contributed exporters for various systems (Datadog, New Relic, Splunk,
    Kafka, Loki, TimescaleDB, etc.).
-   You typically wouldn't need to change `cryostorm` itself; instead, you
    would:
    1.  Configure `cryostorm` to send data via OTLP to the Collector
        (`exporter_type=ExporterType.OTLP`).
    2.  Configure the Collector (`collector-config.yaml`) to use the appropriate
        exporter for your desired backend.

## Flow of llm_app.py (Not say super complete but it's roughly there)

Imagine a single web request hitting your application. Here's how the telemetry
(traces, metrics, logs) generated during that request travels through the
system:

### Phase 1: Telemetry Generation (Inside Your Application via OTel SDK)

Let's break down the execution flow of the
`standalones/instrumentation/demo/llm_app.py` application, rigorously relating
it to Phase 1 (Telemetry Generation in the Application) and the start of Phase 2
(Data Reception by the Collector) as described in your `flow.md` document.

**Phase 1: Telemetry Generation (Inside `llm_app.py`)**

This phase covers everything that happens _within_ the `llm_app.py` process
itself to generate traces, metrics, and logs using the OpenTelemetry SDK.

1.  **Initialization & Configuration (Pre-Runtime & Startup):**

    -   **Loading Configuration:** The application starts by loading environment
        variables from `.env.local` using `load_dotenv`. This file contains
        crucial settings like `OTEL_SERVICE_NAME`, `OTEL_SERVICE_VERSION`,
        `OTEL_EXPORTER_OTLP_ENDPOINT`, etc.
    -   **Settings Management:** `TelemetrySettings()` reads these environment
        variables using Pydantic `BaseSettings`, validating and structuring
        them. This provides a typed configuration object (`settings`) for the
        telemetry system.
    -   **Telemetry Singleton:** `telemetry = Telemetry.from_settings(settings)`
        initializes the core `Telemetry` class. This class acts as a facade and
        central point for interacting with the OpenTelemetry SDK. It likely
        configures the `TracerProvider`, `MeterProvider`, and `LoggerProvider`
        based on the `settings`. It sets up the resource attributes
        (`service.name`, etc.) that will be attached to all telemetry. It also
        configures the exporters (e.g., `OTLPSpanExporter`,
        `OTLPMetricExporter`, `OTLPLogExporter`) pointing to the Collector
        endpoint defined in the settings (`OTEL_EXPORTER_OTLP_ENDPOINT`). It
        also configures processors like the `BatchSpanProcessor`.
    -   **Custom Metric Instruments:** Specific metric instruments are created
        using the initialized `telemetry` object:

        ```python
        llm_request_volume_total = telemetry.create_counter(...)
        llm_request_duration_seconds = telemetry.create_histogram(...)
        # ... other metrics
        ```

        These lines register the metrics with the SDK's `MeterProvider`, making
        them ready for recording values.

    -   **Lifespan Management:** The `lifespan` function ensures telemetry setup
        happens correctly at application startup and shutdown messages are
        logged.

2.  **Instrumentation Activated (Runtime - Request Handling):**

    -   **Middleware:** The `TraceContextMiddleware` is crucial. When a request
        hits the FastAPI app (e.g., `/chat` or `/system-diagnostics`), this
        middleware intercepts it _first_.
        -   It attempts to extract trace context (Trace ID, Parent Span ID) from
            incoming HTTP headers (like `traceparent`).
        -   It then uses `telemetry.start_as_current_span` to create a
            **SERVER** span representing the entire HTTP request processing.
            This span either starts a new trace or continues an existing one if
            context was propagated.
        -   Crucially, it makes this span _active_ in the current execution
            context.
    -   **Automatic & Manual Instrumentation:**
        -   **Automatic:** Libraries instrumented by OpenTelemetry (like `httpx`
            if the instrumentation library is installed, or FastAPI itself via
            the middleware) can automatically create child spans. For example,
            the `httpx.AsyncClient` call within the `/chat` endpoint _could_
            create a CLIENT span automatically if
            `opentelemetry-instrumentation-httpx` is installed and configured.
        -   **Manual:** The code explicitly uses
            `telemetry.start_as_current_span` within route handlers (`/chat`,
            `/system-diagnostics`) and helper functions
            (`simulate_llm_api_call`, `system.gather_metrics` inside
            `/system-diagnostics`) to create specific **INTERNAL** or **CLIENT**
            spans for logical units of work. These become child spans of the
            parent span (often the SERVER span from the middleware).
        -   **Logging Integration:** `telemetry.log(...)` is used throughout.
            This custom logging method likely integrates with Python's standard
            logging but ensures that the current active Span ID and Trace ID are
            automatically attached to the log records before they are processed
            by the OTel `LoggerProvider`.
        -   **Metric Recording:** Calls like
            `llm_request_volume_total.add(...)`,
            `llm_request_duration_seconds.record(...)`,
            `active_chat_sessions.add(...)` are made at specific points to
            record measurements against the metric instruments defined earlier.
            Attributes (key-value pairs like
            `{"model": model, "success": True}`) are attached to provide
            dimensions for the metrics.

3.  **Trace - Span Creation & Hierarchy (Example: `/chat` endpoint):**

    -   **Request In:** A POST request arrives at `/chat`.
    -   **Middleware Span (SERVER):** `TraceContextMiddleware` starts
        `Span 1 (SERVER)` for `HTTP POST /chat`. It extracts trace context from
        headers if present.
    -   **Route Handler Span (INTERNAL):** Inside the `/chat` function,
        `telemetry.start_as_current_span` starts `Span 2 (INTERNAL)` for the
        `chat` operation itself. This is a child of `Span 1`.
    -   **Outgoing HTTP Call (CLIENT - Potentially Auto-Instrumented):** The
        `httpx.AsyncClient().post` call to `/system-diagnostics` happens.
        -   `telemetry.inject_context(carrier)` adds the current trace context
            (from `Span 2`) into the `headers` (`carrier`).
        -   If `httpx` instrumentation is active, it might automatically create
            `Span 3 (CLIENT)` for the `HTTP POST /system-diagnostics` call, as a
            child of `Span 2`. The injected headers ensure the receiving end
            (`/system-diagnostics`) can continue the trace.
    -   **Internal LLM Call Span (CLIENT):** Inside the `chat` function,
        `simulate_llm_api_call` is called.
        -   Inside `simulate_llm_api_call`, `telemetry.start_as_current_span`
            creates `Span 4 (CLIENT)` for `llm.simulate_llm_api_call`. This is a
            child of `Span 2`.
    -   **Span Completion:** As `with` blocks exit or functions return, the
        corresponding spans are ended (calculating their duration). Errors are
        recorded using `span.record_exception(e)` and status set with
        `span.set_status(...)`. Events are added using `span.add_event(...)`.

4.  **Metrics Recording (Examples from `simulate_llm_api_call`):**

    -   `temperature_distribution.record(temperature, {"model": model})`
    -   `top_p_distribution.record(top_p, {"model": model})`
    -   `llm_token_input_total.add(input_tokens, {"model": model, "session.id": session_id})`
    -   `llm_request_duration_seconds.record(api_latency, {"model": model, "success": True})`
        (or `False` on error)
    -   `error_counter.add(1, {"error.type": "llm_api_timeout", "model": model})`
        (on error)
    -   `llm_token_output_total.add(output_tokens, {"model": model, "session.id": session_id})`
    -   `llm_request_cost_total.add(total_cost, {"model": model, "session.id": session_id})`

5.  **Logging (Examples):**

    -   `telemetry.log(level=logging.INFO, message="Starting LLM API simulation service", ...)`
        (during lifespan startup)
    -   `telemetry.log(level=logging.INFO, message=f"Processing LLM request...", ...)`
        (inside `simulate_llm_api_call`)
    -   `telemetry.log(level=logging.ERROR, message=f"LLM API timeout: {error!s}", ...)`
        (on error)
    -   These logs automatically get correlation metadata (Trace ID, Span ID)
        added by the `Telemetry` class's logging setup before being handed to
        the OTel SDK's `LoggerProvider`.

6.  **Resource Attributes:** The `service.name`, `service.version`,
    `deployment.environment` (and potentially others like
    `telemetry.sdk.language`, `telemetry.sdk.version`) configured in
    `TelemetrySettings` and set up by `Telemetry.from_settings` are
    automatically attached to _all_ outgoing spans, metrics, and log records
    originating from this `llm_app.py` process.

7.  **SDK Processing & Batching (Internal SDK Behavior):**

    -   **Spans:** Completed spans are passed to the `BatchSpanProcessor`
        (configured implicitly or explicitly by the `Telemetry` class). This
        processor collects spans in memory.
    -   **Metrics:** The `MeterProvider` (managed by `Telemetry`) aggregates
        metric recordings. A `PeriodicExportingMetricReader` (a common default,
        likely configured by `Telemetry`) periodically collects the aggregated
        values (e.g., sum for counters, histogram buckets) from all instruments.
    -   **Logs:** Log records captured by the configured OTel logging handler
        are sent to a `BatchLogRecordProcessor`.
    -   **Batching:** All three processors (span, metric, log) hold their
        respective data items until either a configured time interval elapses
        (e.g., `OTEL_BSP_SCHEDULE_DELAY`, default 5s) or a maximum batch size is
        reached (e.g., `OTEL_BSP_MAX_EXPORT_BATCH_SIZE`, default 512).

8.  **SDK Exporting (OTLP):**
    -   Once a batch is ready in any of the processors, the corresponding
        exporter (e.g., `OTLPSpanExporter`, `OTLPMetricExporter`,
        `OTLPLogExporter`, all configured by `Telemetry` based on `settings`)
        takes the batch.
    -   The exporter serializes the batch into the OTLP format (Protobuf).
    -   It sends the serialized data over the network (using gRPC or HTTP, based
        on `OTEL_EXPORTER_OTLP_PROTOCOL`) to the configured Collector endpoint
        (`OTEL_EXPORTER_OTLP_ENDPOINT`, e.g., `http://localhost:4317` or
        `http://localhost:4318`). This network transmission marks the end of
        Phase 1 for that batch of data.

### Phase 2: Data Reception & Processing (Inside OTel Collector - The Very

Beginning)

This phase starts the moment the data _sent_ by the `llm_app.py` SDK exporters
arrives at the OpenTelemetry Collector.

9.  **Collector - OTLP Receiver:**

    -   The OTel Collector service (running separately, likely via
        `docker-compose-local.yml`) is configured with an `otlp` receiver in its
        `collector-config.yaml`.
    -   This receiver listens on the ports specified (e.g., 4317 for gRPC, 4318
        for HTTP).
    -   It accepts the incoming network connection(s) from the `llm_app.py` OTLP
        exporters.

10. **Collector - Deserialization & Identification:**

    -   The OTLP receiver parses the incoming Protobuf messages sent by
        `llm_app.py`.
    -   It identifies the signal type (traces, metrics, or logs) based on the
        OTLP message structure.
    -   It converts the data into the Collector's internal representation. The
        resource attributes (`service.name`, etc.) sent by the SDK are
        preserved.

11. **Collector - Pipeline Entry:**
    -   The receiver now routes the deserialized data to the _start_ of the
        relevant pipeline defined in the `service:` section of
        `collector-config.yaml`.
        -   Trace data (originating from `telemetry.start_as_current_span`) goes
            to the `traces:` pipeline.
        -   Metric data (originating from `.add()` and `.record()` calls) goes
            to the `metrics:` pipeline.
        -   Log data (originating from `telemetry.log()`) goes to the `logs:`
            pipeline.

From this point, the data flows through the processors (like `batch`,
`memory_limiter`, `resource`) and finally to the exporters (`otlp/jaeger`,
`prometheus`, `debug`) defined _within the Collector's configuration_, as
detailed in the later steps of Phase 2 and Phase 3 of your `flow.md`. The
`llm_app.py` application's direct involvement ends once the SDK successfully
exports the data (Step 8).

8.  **SDK Exporting (OTLP):** Once a batch is ready, the configured `Exporter`
    (e.g., `OTLPSpanExporter`, `OTLPMetricExporter`, `OTLPLogExporter`) takes
    the batched data. It serializes the data into the OTLP (OpenTelemetry
    Protocol) format (usually using Protobuf) and sends it over the network
    (gRPC on port 4317 or HTTP on port 4318, as configured) to the OTel
    Collector's address.

**Phase 2: Data Reception & Processing (Inside OTel Collector)**

9.  **Collector - OTLP Receiver:** The OTel Collector service is listening for
    incoming connections on the ports specified in its configuration
    (`docker-compose.yaml` exposes 4317 and 4318). The `receivers` section
    (specifically the `otlp` receiver) accepts the gRPC or HTTP connection from
    your application's SDK.
10. **Collector - Deserialization & Identification:** The OTLP receiver parses
    the incoming Protobuf messages. It understands the OTLP structure and
    identifies whether the incoming data contains traces, metrics, or logs based
    on the message type. It converts this data into the Collector's internal
    data model.
11. **Collector - Pipeline Entry:** The receiver now routes the internal data
    objects to the _beginning_ of the appropriate pipeline(s) defined in the
    `service:` section of the Collector's configuration
    (`collector-config.yaml`).
    -   Trace data goes to the `traces:` pipeline.
    -   Metric data goes to the `metrics:` pipeline.
    -   Log data goes to the `logs:` pipeline. These pipelines operate
        independently.
12. **Collector - Processing Pipeline (Example: Traces):** The data flows
    sequentially through the processors defined for that pipeline
    (`pipelines.traces.processors: [...]`).
    -   **`memory_limiter`:** (Often first) Checks the Collector's current
        memory usage against configured limits (`limit_mib`). If usage is too
        high, it starts refusing data (triggering backpressure) or dropping data
        to prevent crashing. This usually happens _before_ expensive processing.
    -   **`batch`:** (Commonly used) Collects spans/metrics/logs arriving at the
        Collector. Like the SDK batching, it waits for a timeout (`timeout`) or
        batch size (`send_batch_size`) before flushing the batch to the _next_
        processor or exporter. This improves efficiency for exporting.
    -   **`resource`:** Can add, modify, or overwrite resource attributes. For
        instance, it might add Kubernetes metadata (`k8s.pod.name`) if running
        in K8s, or ensure `deployment.environment` is set consistently.
    -   **(Other Processors):** Other processors could exist here (e.g.,
        `attributes/filter` to drop certain spans, `spanmetrics` to generate
        metrics _from_ spans).
13. **Collector - Processing Pipeline (Metrics & Logs):** Similar processing
    steps occur in the `metrics` and `logs` pipelines, using their respective
    processor configurations. They also likely have `memory_limiter` and `batch`
    processors.

### Phase 3: Data Exporting (From OTel Collector to Backends)

14. **Collector - Reaching Exporters:** After passing through all processors in
    a pipeline, the (potentially transformed and batched) data reaches the
    exporters defined for that pipeline (`pipelines.traces.exporters: [...]`).
15. **Collector - Exporting Traces:**
    -   **`otlp/jaeger`:** The trace batch is handed to the OTLP exporter
        configured to send to Jaeger. It makes a gRPC call (usually) to the
        Jaeger endpoint defined in its configuration (e.g.,
        `endpoint: jaeger:4317` in the Collector config, matching the Jaeger
        service in `docker-compose.yaml`). If the connection fails, this
        exporter typically has built-in retry logic (with backoff).
    -   **`debug`:** Concurrently, the same trace batch is sent to the debug
        exporter, which simply prints the content of the spans to the
        Collector's standard output or log file. This is invaluable for
        confirming data reaches the Collector, even if the backend (Jaeger) is
        down.
16. **Collector - Exporting Metrics:**
    -   **`prometheus`:** The metrics batch updates the internal state of the
        Prometheus exporter within the Collector. This exporter doesn't _push_
        metrics. Instead, it exposes an HTTP endpoint (e.g.,
        `otel-collector:8889`, as defined in the Collector config and exposed in
        `docker-compose.yaml`). When the separate Prometheus _server_ scrapes
        this endpoint (based on its own `prometheus.yml` configuration), the
        exporter formats the current metrics into the Prometheus text exposition
        format and returns them in the HTTP response.
    -   **`debug`:** The metrics batch is also printed to the Collector's
        console.
17. **Collector - Exporting Logs:**
    -   **`debug`:** In your example, the logs pipeline likely only has the
        `debug` exporter, so the log records are printed to the Collector's
        console. If other exporters were configured (e.g., `otlp` to send to
        Loki, `loki`, `file`), the logs would be sent there as well, potentially
        with retries.

### Phase 4: Backend Storage & Visualization

18. **Jaeger:** The Jaeger service (running in its own container) receives the
    OTLP trace data from the Collector. It parses these spans and stores them
    (in-memory in the default dev setup, or potentially a database like
    Elasticsearch/Cassandra in production). You can then use the Jaeger UI (port
    `16686` in `docker-compose.yaml`) to query, visualize, and analyze the
    distributed traces.
19. **Prometheus:** The Prometheus server (running in its container)
    periodically sends an HTTP GET request (scrapes) to the Collector's
    Prometheus exporter endpoint (`otel-collector:8889`). It receives the
    metrics in text format, parses them, and stores them in its time-series
    database. You can query these metrics using PromQL via the Prometheus UI
    (port `9090`) or visualize them using Grafana (if configured).
20. **Logs (Debug):** The logs exported via the `debug` exporter are simply
    visible in the logs of the `otel-collector` container
    (`docker logs otel-collector`). If a real logging backend were used (Loki,
    Elasticsearch), they would be stored and searchable there.

### Phase 5: Lifecycle & Reliability

-   **Continuous Flow:** This entire process runs continuously for every request
    and background task generating telemetry.
-   **Health & Monitoring:** The `health_check` extension (port `13133`) allows
    external systems (like Docker or Kubernetes) to verify the Collector is
    alive and responsive. The Collector can also expose its _own_ internal
    metrics via Prometheus (port `8888`) for monitoring its performance (memory
    usage, queue lengths, export success/failure rates).
-   **Resilience:**
    -   **Batching:** Reduces load on backends and network traffic.
    -   **Memory Limiter:** Prevents the Collector from crashing due to
        excessive memory consumption under heavy load, enabling graceful
        degradation.
    -   **Retries:** OTLP exporters (and others) often have built-in retry
        mechanisms with exponential backoff to handle temporary network issues
        or backend unavailability.
    -   **Backpressure:** If an exporter's queue fills up (e.g., Jaeger is down
        and retries are failing), the memory limiter can signal backpressure,
        potentially causing the OTLP receiver to signal back to the SDK, which
        might then slow down or temporarily drop data.

This detailed flow shows how telemetry moves from its origin in your
application, through the flexible processing and routing capabilities of the
OTel Collector, and finally lands in specialized backend systems for analysis
and visualization, with mechanisms built in for efficiency and reliability.

---

## Anatomy of Telemetry Flow (Revisited from concept.md)

Bringing it all together, let’s walk through how data flows end-to-end in this
OpenTelemetry setup, from the application to the backends, across the trace,
metric, and log pipelines:

1. **Application generates telemetry:** The instrumented application (Python
   SDK) executes some business logic – for example, it handles an incoming web
   request. During that request, the OTel tracer starts a new span (representing
   the request handling). Perhaps some database calls inside create child spans.
   Simultaneously, metrics (like request count, latency) are recorded, and logs
   (like an info log of the request) are written. All these signals are captured
   by the OpenTelemetry SDK in-process. When the request is done, the spans end
   and are sent to the SDK’s exporter; metrics are updated and, if the export
   interval arrives, are dispatched; logs are forwarded by the logging exporter.
   At this point, the telemetry leaves the process over the network via OTLP.

2. **Data sent over OTLP to Collector:** The telemetry data (spans, metrics,
   logs) travels to the Collector’s OTLP receiver. If using OTLP/gRPC, this is a
   continuous gRPC stream; if OTLP/HTTP, individual HTTP requests for each
   batch. In either case, the data arrives at the Collector on the designated
   port. The Collector’s OTLP receiver accepts the incoming connections and
   starts receiving the bytes. Because OTLP encodes which signal type each
   message contains (there are distinct request message types for traces,
   metrics, logs), the receiver knows how to handle each incoming payload. It
   parses the Protobuf and converts (deserializes) it into the Collector’s
   internal representation (which is very similar to OTLP data model objects).

3. **Routing to pipelines:** The OTLP receiver then emits the data into the
   appropriate pipelines. A single OTLP receiver can feed multiple pipelines:
   trace data is fed into the trace pipeline, metrics into the metrics pipeline,
   logs into the logs pipeline. These pipelines operate in parallel and are
   independent. In our case, since we have all three pipelines configured, the
   receiver will push each span to the trace pipeline’s processors, each metric
   to the metrics processors, etc. This separation is logical – under the hood,
   the Collector might use separate goroutines or queues per pipeline. The key
   is that a large volume of trace data won’t block metrics, and vice versa,
   because of this separation.

4. **Processing in pipelines:** Once in a pipeline, the data passes through the
   processors in order. Taking the **trace pipeline** as an example: as spans
   come in, the memory limiter first checks if the Collector is within memory
   limits. Assuming we’re fine (in normal conditions), it forwards the spans.
   Next, the batch processor will collect spans for a short duration (say up to
   5 seconds or 10000 spans) before flushing them onward. So if 50 spans come in
   almost at once, the batch processor might let them accumulate briefly. When
   time or count threshold hits, it bundles those 50 spans as a batch. The
   **resource processor** then runs, adding any missing resource attributes
   (e.g. it tags each span in that batch with service.name="myapp" if not
   already set). Now the spans are enriched and ready to leave the Collector.
   Similarly, in the **metrics pipeline**, incoming metric data points might be
   buffered by batch (commonly metrics batch by time, so they align with scrape
   intervals or exporter pushes), and the memory limiter would drop metrics only
   if we’re over memory. The resource processor could tag metrics (for example,
   add `deployment.environment=prod` to all metrics). In the **logs pipeline**,
   log records go through batch (maybe grouping multiple logs before export) and
   get resource attributes as well. Note that the memory limiter, if triggered,
   could start dropping data here – for instance, if an avalanche of spans came
   in and memory usage spiked, the memory limiter might refuse some spans. In
   that case it signals backpressure to the OTLP receiver, which in turn would
   cause the SDK to retry sending later
   ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=The%20memory%20limiter%20can%20be,down%20to%20retries%20with%20backoff)).
   Under normal operation, though, all data flows through.

5. **Exporting to backends:** After processing, each pipeline’s data reaches its
   exporters. In the **trace pipeline**, our spans batch is handed off to two
   exporters: the OTLP/Jaeger exporter and the debug exporter. The Collector
   makes a gRPC call to the Jaeger collector at `jaeger:4317` (for example) and
   transmits the span batch. If Jaeger is up and returns OK, those spans are now
   stored by Jaeger, and you can view them in the Jaeger UI. Concurrently, the
   debug exporter logs those spans locally – you’d see a log line for each span
   (with its trace ID, name, etc.) in the Collector’s console or log file. The
   two happen in parallel, so even if (for example) the Jaeger exporter had a
   network hiccup and was retrying, the debug exporter would still log the span
   (this helps confirm the data made it into the Collector even if the backend
   is down). In the **metrics pipeline**, the metrics batch goes to Prometheus
   exporter and debug. The debug exporter will log something like a metric data
   object (e.g. “Metric[name=request_count, value=123]”). The Prometheus
   exporter, however, doesn’t “send” the metrics anywhere at that moment; it
   simply updates its internal state to include the latest metrics. When a
   Prometheus server later scrapes, those metrics will be output. So you can
   think of the act of exporting for Prometheus as “storing the metrics for
   later pull”. We should also consider that right after the Collector updates
   the Prometheus exporter with new metric values, if a Prometheus server is
   already polling on an interval, it might immediately do a scrape. During a
   scrape, the Prometheus exporter will format all the current metrics
   (including the ones just received) into text and serve them over HTTP. Thus,
   the data gets into Prometheus backend. If multiple scrapes happen, the
   metrics will be served each time with whatever the latest values are (the
   exporter can hold cumulative metrics or last values depending on type,
   ensuring, for example, counters only ever increase). Finally, in the **logs
   pipeline**, the log records go to the debug exporter, which will print them
   out (perhaps with timestamp, severity, body of the log, etc.). If there were
   another log exporter (say to Elastic or Splunk) configured, it would send
   logs there too. In our current config, we only have debug for logs, so
   effectively the Collector just prints the logs it receives.

6. **Lifecycle and reliability:** Each of these pipelines runs continuously as
   long as the Collector is running. The health_check extension can be used by
   an orchestrator to verify the Collector hasn’t died while this is happening.
   The batch processor ensures that if traffic is low, data isn’t delayed too
   long (timeout ensures it sends whatever it has), and if traffic is high, data
   is broken into manageable chunks. The memory limiter ensures that if
   exporters can’t keep up (e.g. Jaeger is down and the Collector’s sending
   queue is filling up), at some point data will be shed to protect the process.
   The exporters themselves often have retry logic internally. For instance, the
   OTLP exporter will retry sending to Jaeger if the first attempt fails (with
   exponential backoff) – it’s actually implemented with a queue and a retry
   mechanism internally
   ([OTel Collector - Blog by Roman Glushko](https://www.romaglushko.com/blog/opentelemetry-collector/#:~:text=Exporters)).
   This means transient failures to the backend won’t necessarily lose spans;
   they’ll be retried for some duration. The debug exporter doesn’t retry (it’s
   just logging), and Prometheus exporter doesn’t need retry (the onus is on
   Prometheus server to retry scrapes if it fails). So the whole system is built
   with resiliency in mind: caching, batching, backpressure, and retries all
   working together.
