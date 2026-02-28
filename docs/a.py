"""
**Core Purpose:** This module acts as the central **Facade** and
**Initialization Orchestrator** for the entire OpenTelemetry instrumentation
setup within the application. It provides a single, simplified interface for
configuring, initializing, accessing, and shutting down all telemetry components
(tracing, metrics, logging, propagation, resource).

**Functionality:**

1.  **Builder Pattern (`TelemetryBuilder`):** Implements the Builder pattern to
    construct the various telemetry components (`Resource`,
    `PropagatorComponent`, `TracingComponent`, `MetricsComponent`,
    `LoggingComponent`) step-by-step, ensuring dependencies are met (e.g.,
    `Resource` is needed before tracing/metrics/logging). It uses the respective
    factories (`ResourceFactory`, `PropagatorFactory`, etc.) defined in other
    modules, taking the global `TelemetrySettings` as input.
2.  **Component Container (`TelemetryComponents`):** A Pydantic `BaseModel` used
    by the `TelemetryBuilder` to return a structured container holding all the
    successfully built component instances. It provides convenience methods
    (`setup_all`, `shutdown_all`) to manage the lifecycle of the contained
    components in the correct order.
3.  **Singleton Facade (`Telemetry`):**
    -   **Facade Pattern:** Presents a simplified, unified API to the complex
        underlying telemetry system. Application code interacts primarily with
        the `Telemetry` instance (e.g., `telemetry.tracer`, `telemetry.meter`,
        `telemetry.logger`, `telemetry.traced(...)`) instead of directly
        managing the individual components or SDK details.
    -   **Singleton Pattern:** Ensures only one instance of the `Telemetry`
        class exists throughout the application lifecycle. This is crucial
        because OpenTelemetry relies on global providers (`set_tracer_provider`,
        `set_meter_provider`, etc.). The singleton manages this global state
        safely using thread locks (`RLock`) to prevent race conditions during
        initialization.
    -   **Initialization:** The `__new__` and `__init__` methods work together
        with the `_initialize` method and locks to ensure that the telemetry
        system (using the `TelemetryBuilder`) is set up exactly once when the
        singleton is first created or accessed with settings. It handles
        potential initialization errors gracefully.
    -   **Accessor Properties:** Provides properties (`.tracer`, `.meter`,
        `.propagator`, `.logger`) to easily retrieve the configured OTel objects
        (or `None`/No-Op equivalents if not initialized).
    -   **Convenience Methods:** Offers helper methods that wrap common OTel
        operations, adding initialization checks and fallback behavior (No-Op
        spans/metrics):
        -   `start_as_current_span`: Context manager for creating spans.
        -   `create_counter`/`histogram`/`up_down_counter`: For creating metric
            instruments.
        -   `log`: For emitting logs via the trace-aware logger.
        -   `inject_context`/`extract_context`: For manual context propagation.
    -   **`@traced` Decorator:** A powerful decorator to automatically wrap
        synchronous or asynchronous function calls in spans, handling span
        naming, kinds, attributes, and exception recording.
    -   **Lifecycle Management:** Provides `shutdown` and `reset` methods to
        gracefully shut down the telemetry components (flushing buffers) and
        optionally reset the singleton state (useful for testing).

**Why it's important:** This module is the primary entry point for integrating
and using OpenTelemetry within the application. It hides the complexity of
setting up multiple SDK components and provides a clean, high-level API. The
Singleton pattern ensures consistent global configuration, while the Facade
simplifies usage. The Builder pattern makes the initialization process robust
and dependency-aware. Convenience methods like `@traced` significantly reduce
the boilerplate code required for common instrumentation tasks.
"""

# What: Imports the 'annotations' feature for postponed evaluation of type hints.
from __future__ import annotations

# What: Imports collections.abc for Abstract Base Classes related to collections.
# Why: Specifically used here for `collections.abc.Generator` (for the context manager return type)
#      and potentially `collections.abc.Callable` and `Awaitable` (though `typing` versions exist).
import collections.abc

# What: Imports functools for higher-order functions and operations on callable objects.
# Why: Used here for `functools.wraps`, which is crucial for decorators (`@traced`) to
#      preserve the metadata (like `__name__`, `__doc__`) of the original function.
import functools

# What: Imports inspect for introspection capabilities (examining properties of objects).
# Why: Used in the `@traced` decorator to determine if the decorated function is
#      asynchronous (`inspect.iscoroutinefunction`).
import inspect

# What: Imports Python's standard logging module.
# Why: The Telemetry facade provides access to a configured logger.
import logging

# What: Imports the threading module for synchronization primitives.
# Why: Used for `threading.RLock` to ensure thread-safe initialization and access
#      to the singleton Telemetry instance.
import threading

# What: Imports traceback for working with stack traces.
# Why: Used during initialization error handling to format and raise exceptions
#      with the original traceback for better debugging.
import traceback

# What: Imports specific types from collections.abc (potentially redundant with `typing`).
# Why: Explicitly imports `Awaitable` and `Callable` for type hinting asynchronous
#      functions and general callables, especially within the `@traced` decorator.
from collections.abc import (
    Awaitable,
    Callable,
)  # Use `typing.Awaitable`, `typing.Callable` usually

# What: Imports contextlib for utilities creating and working with context managers.
# Why: Used for `@contextmanager`, a decorator that simplifies creating context managers
#      (like `start_as_current_span`) using generator functions.
from contextlib import contextmanager

# What: Imports various types from the `typing` module.
# Why:
#   - `Any`: For flexible type hints where specificity isn't needed or possible.
#   - `ClassVar`: To denote class-level variables (singleton instance, lock).
#   - `Self`: For type hinting methods returning an instance of their own class (Python 3.11+).
#   - `cast`: To hint to the type checker about a type change, primarily in decorators.
#   - `final`: To indicate a class should not be subclassed (PEP 591).
#   - `overload`: To define multiple signatures for the same function, enhancing type
#                 checking for functions/methods that behave differently based on input types
#                 (like the `@traced` decorator handling sync/async functions).
from typing import (
    Any,
    ClassVar,
    Self,
    cast,
    final,
    overload,
)  # Use `typing_extensions.Self` etc < 3.11

# What: Imports the top-level `metrics` and `trace` modules from OpenTelemetry API.
# Why: To access API functions like `get_meter`, `get_tracer`, and core types.
from opentelemetry import metrics, trace

# What: Imports the No-Op Meter implementation.
# Why: Used as a fallback/default when metrics are disabled or not initialized,
#      ensuring that calls to create metric instruments don't crash the application.
from opentelemetry.metrics import NoOpMeter

# What: Imports the base class for text map propagators.
# Why: Used for type hinting the `propagator` property.
from opentelemetry.propagators.textmap import TextMapPropagator

# What: Imports Resource-related types from OTel SDK.
# Why: Used for type hinting (`Attributes`, `Resource`) and creating spans (`Attributes`).
from opentelemetry.sdk.resources import Attributes, Resource

# What: Imports core types from the OTel Trace API.
# Why:
#   - `Context`: Represents the propagation context (used in `start_as_current_span`).
#   - `NoOpTracer`: Fallback tracer used when tracing is disabled/uninitialized.
#   - `SpanKind`: Enum specifying the type of span (e.g., SERVER, CLIENT, INTERNAL).
#   - `_Links`: Type hint for links between spans (less common usage).
from opentelemetry.trace import Context, NoOpTracer, SpanKind, _Links

# What: Imports base classes from Pydantic.
# Why:
#   - `BaseModel`: Used for `TelemetryComponents` to create a structured data container
#                  with validation (though validation isn't heavily used here).
#   - `ConfigDict`: Used to configure Pydantic model behavior (`arbitrary_types_allowed`).
from pydantic import (
    BaseModel,
    ConfigDict,
)  # Note: Pydantic is used here, ensure it's intended

# What: Imports the base interface for telemetry components.
# Why: Used by `TelemetryComponents` to iterate over components for setup/shutdown.
from instrumentation.interface import TelemetryComponent

# What: Imports the concrete logging component setup class.
from instrumentation.log import LoggingComponent

# What: Imports the concrete metrics component setup class.
from instrumentation.metric import MetricsComponent

# What: Imports the concrete propagator component and its factory.
from instrumentation.propagator import PropagatorComponent, PropagatorFactory

# What: Imports the concrete resource factory.
from instrumentation.resource import ResourceFactory

# What: Imports the main settings class.
from instrumentation.settings import TelemetrySettings

# What: Imports the concrete tracing component setup class.
from instrumentation.trace import TracingComponent

# What: Imports reusable type variables (ParamSpec, TypeVar) for generic decorators.
from instrumentation.types_ import AsyncR, P, R


# What: Defines a Builder class for constructing the Telemetry system.
# Why: Implements the Builder pattern. This pattern separates the complex construction
#      of an object (the complete Telemetry setup) from its representation. It allows
#      step-by-step construction and ensures dependencies are met (e.g., Resource
#      must be built before Tracing/Metrics).
class TelemetryBuilder:
    """Builder for configuring and creating a telemetry instance."""

    # What: Constructor, takes the global settings object.
    def __init__(self, settings: TelemetrySettings) -> None:
        self.settings = settings
        # Initialize attributes to hold the built components
        self.resource: Resource | None = None
        self.propagator_component: PropagatorComponent | None = None
        self.tracing_component: TracingComponent | None = None
        self.metrics_component: MetricsComponent | None = None
        self.logging_component: LoggingComponent | None = None

    # What: Method to build the Resource component.
    # How it works: Creates the factory from settings, creates the resource, stores it.
    # Returns: `Self` to allow method chaining (fluent interface).
    def build_resource(self) -> Self:
        """Builds the OpenTelemetry Resource."""
        print("Builder: Building Resource...")  # Added print
        factory = ResourceFactory.from_settings(self.settings)
        self.resource = factory.create()
        print(f"Builder: Resource built: {self.resource.attributes}")  # Added print
        return self

    # What: Method to build the Propagator component.
    # How it works: Creates the factory, creates the component, stores it.
    def build_propagator(self) -> Self:
        """Builds the PropagatorComponent."""
        print("Builder: Building Propagator...")  # Added print
        factory = PropagatorFactory.from_settings(self.settings)
        self.propagator_component = PropagatorComponent(factory)
        print("Builder: Propagator built.")  # Added print
        return self

    # What: Method to build the Tracing component.
    # Dependency: Requires Resource to be built first.
    def build_tracing(self) -> Self:
        """Builds the TracingComponent."""
        print("Builder: Building Tracing...")  # Added print
        if not self.resource:
            print(
                "Builder: Error - Resource needed for Tracing, building Resource first."
            )  # Added print
            self.build_resource()  # Build resource if not already built
            # raise ValueError("Resource must be built before tracing") # Original logic

        # Assertion to satisfy type checker after potential build_resource call
        assert self.resource is not None, "Resource should be available now"

        self.tracing_component = TracingComponent.from_settings(
            self.settings,
            self.resource,
        )
        print("Builder: Tracing built.")  # Added print
        return self

    # What: Method to build the Metrics component.
    # Dependency: Requires Resource to be built first.
    def build_metrics(self) -> Self:
        """Builds the MetricsComponent."""
        print("Builder: Building Metrics...")  # Added print
        if not self.resource:
            print(
                "Builder: Error - Resource needed for Metrics, building Resource first."
            )  # Added print
            self.build_resource()
            # raise ValueError("Resource must be built before metrics") # Original logic

        assert self.resource is not None, "Resource should be available now"

        self.metrics_component = MetricsComponent.from_settings(
            self.settings,
            self.resource,
        )
        print("Builder: Metrics built.")  # Added print
        return self

    # What: Method to build the Logging component.
    # Dependency: Requires Resource to be built first.
    def build_logging(self) -> Self:
        """Builds the LoggingComponent."""
        print("Builder: Building Logging...")  # Added print
        if not self.resource:  # Added check similar to others
            print(
                "Builder: Error - Resource needed for Logging, building Resource first."
            )  # Added print
            self.build_resource()

        assert self.resource is not None, "Resource must be built before logging"
        self.logging_component = LoggingComponent.from_settings(
            self.settings, self.resource
        )
        print("Builder: Logging built.")  # Added print
        return self

    # What: Final method to construct the `TelemetryComponents` container.
    # Why: Ensures all necessary components are built (calling build methods if needed)
    #      and then packages them into a single data structure.
    # Returns: A `TelemetryComponents` instance holding all configured components.
    def build(self) -> TelemetryComponents:
        """Build all components based on their dependencies and return the container."""
        print("Builder: Finalizing build...")  # Added print
        # Ensure all components are built, calling build methods if they haven't been explicitly called.
        if not self.resource:
            self.build_resource()
        if not self.propagator_component:
            self.build_propagator()
        if not self.tracing_component:
            self.build_tracing()
        if not self.metrics_component:
            self.build_metrics()
        if not self.logging_component:
            self.build_logging()

        # Assertions to assure type checker that components are non-None now
        assert self.resource is not None
        assert self.propagator_component is not None
        assert self.tracing_component is not None
        assert self.metrics_component is not None
        assert self.logging_component is not None

        print(
            "Builder: All components built. Creating TelemetryComponents container."
        )  # Added print
        # Create the Pydantic model holding all components.
        # `type: ignore` might be needed if the static checker can't follow the build logic guarantees.
        return TelemetryComponents(
            resource=self.resource,
            propagator=self.propagator_component,
            tracing=self.tracing_component,
            metrics=self.metrics_component,
            logging=self.logging_component,
        )


# What: Defines a Pydantic BaseModel to act as a container for the initialized telemetry components.
# Why: Provides a structured way to hold and pass around the set of active telemetry components.
#      Using Pydantic allows for potential future validation or configuration features.
class TelemetryComponents(BaseModel):
    # What: Pydantic model configuration.
    # Why: `arbitrary_types_allowed=True` is necessary because the model holds complex
    #      objects (like Resource, TracingComponent) that Pydantic doesn't validate by default.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # What: Fields to hold each initialized telemetry component.
    resource: Resource
    propagator: PropagatorComponent
    tracing: TracingComponent
    metrics: MetricsComponent
    logging: LoggingComponent

    # What: Method to call `setup()` on all relevant components.
    # Why: Provides a single point to initialize the OTel SDKs based on the built components.
    def setup_all(self) -> None:
        """Set up all telemetry components in the correct order."""
        print("TelemetryComponents: Setting up all components...")  # Added print
        # Define setup order (Propagator first, then others)
        # NOTE: Order might matter depending on interdependencies, e.g., setting global propagator before tracers use it.
        components: list[TelemetryComponent] = [
            self.propagator,
            self.tracing,
            self.metrics,
            self.logging,
        ]
        for component in components:
            print(
                f"TelemetryComponents: Setting up {component.__class__.__name__}..."
            )  # Added print
            component.setup()
        print("TelemetryComponents: All components set up.")  # Added print

    # What: Method to call `shutdown()` on all relevant components.
    # Why: Provides a single point to gracefully shut down the OTel SDKs.
    def shutdown_all(self) -> None:
        """Shut down all telemetry components in the correct order."""
        print("TelemetryComponents: Shutting down all components...")  # Added print
        # Define shutdown order (generally reverse of setup, consider dependencies)
        # Propagator shutdown is usually trivial, others (esp. batch processors) are important.
        components: list[TelemetryComponent] = [
            self.tracing,
            self.metrics,
            self.logging,
            self.propagator,
        ]
        for component in components:
            print(
                f"TelemetryComponents: Shutting down {component.__class__.__name__}..."
            )  # Added print
            try:
                component.shutdown()
            except Exception as e:
                # Log shutdown errors but continue shutting down others
                print(f"ERROR shutting down {component.__class__.__name__}: {e}")
        print("TelemetryComponents: All components shut down.")  # Added print


# What: Defines the main Telemetry class, marked as `final` (cannot be subclassed).
# Why: Implements the Facade pattern and Singleton pattern. It provides a simplified,
#      unified interface (`Telemetry`) to the complex underlying telemetry subsystem
#      (the various components). The Singleton ensures only one instance manages the
#      telemetry setup for the application.
@final
class Telemetry:
    """Main facade for OpenTelemetry instrumentation (Singleton)."""

    # --- Singleton Implementation ---
    # What: Class variables to hold the single instance, lock, initialization flag, and settings.
    _instance: ClassVar[Telemetry | None] = None
    _lock: ClassVar[threading.RLock] = threading.RLock()
    ## Thread-safe access, use RLock because reentrant lock is better if the same thread
    ## enters __new__ and __init__
    _initialized: ClassVar[bool] = False  # Flag to track if setup ran
    _settings: ClassVar[TelemetrySettings | None] = (
        None  # Store settings used for initialization
    )

    # What: Overrides __new__ to control instance creation (Singleton pattern).
    # Why: Ensures only one instance of Telemetry is ever created.
    # How it works: Uses a lock for thread safety. If no instance exists, it creates one
    #              using `super().__new__(cls)` and stores the settings. Subsequent calls
    #              return the existing instance.
    def __new__(
        cls: type[Telemetry], settings: TelemetrySettings | None = None
    ) -> Telemetry:
        # Double-checked locking pattern (check without lock first for performance) - optional
        # if cls._instance is not None:
        #     return cls._instance

        with cls._lock:
            if cls._instance is None:
                print("Telemetry Singleton: Creating new instance.")  # Added print
                if settings is None:
                    # Must provide settings on the first creation call.
                    raise ValueError(
                        "Settings must be provided for the first Telemetry initialization"
                    )
                cls._settings = settings  # Store settings used for the singleton
                cls._instance = super().__new__(cls)
                # Note: Initialization logic moved to __init__ and _initialize
            # else: # Added else for clarity
            # print("Telemetry Singleton: Returning existing instance.") # Added print
        return cls._instance

    # What: The initializer for the Telemetry instance.
    # Why: Called *every time* `Telemetry()` is invoked after `__new__`. Needs to handle
    #      being called multiple times on the same singleton instance.
    # How it works: Uses a lock and the `_initialized` flag to ensure the actual
    #              initialization logic (`_initialize`) runs only once.
    def __init__(self, settings: TelemetrySettings | None = None) -> None:
        # If already initialized by a previous call, do nothing.
        if self.__class__._initialized:
            print(
                "Telemetry Singleton: Already initialized, skipping __init__ logic."
            )  # Added print
            return

        # Use lock to ensure thread-safe initialization sequence.
        with self.__class__._lock:
            # Double-check initialization flag inside the lock.
            if self.__class__._initialized:
                return

            print("Telemetry Singleton: Running initialization...")  # Added print
            # If settings weren't passed to this specific __init__ call, use the
            # settings stored during __new__ (the ones used to create the singleton).
            if settings is None:
                settings = self.__class__._settings
                # This check should technically be redundant due to the check in __new__
                if settings is None:
                    raise ValueError(
                        "Settings must be provided either during __new__ or __init__ on first call"
                    )

            self.settings: TelemetrySettings = settings  # Assign settings to instance
            self.components: TelemetryComponents | None = None  # Holds built components
            self._logger = logging.getLogger(
                __name__
            )  # Internal logger for Telemetry class itself

            # Call the internal initialization method.
            self._initialize()

    # What: Internal method containing the actual one-time initialization logic.
    # Why: Separates the initialization steps from the __init__ boilerplate.
    # Returns: `Self` to potentially allow chaining if needed (though not used here).
    def _initialize(self) -> Self:
        """Performs the actual one-time initialization using the Builder."""
        # This check prevents re-running if _initialize is somehow called directly again.
        if self.__class__._initialized:
            return self

        print("Telemetry Singleton: Executing _initialize...")  # Added print
        try:
            # Use the Builder to construct all components based on settings.
            builder = TelemetryBuilder(self.settings)
            self.components = (
                builder.build()
            )  # Build returns the TelemetryComponents container

            # Call setup on all built components (propagator, tracing, metrics, logging).
            self.components.setup_all()

            # Mark the singleton as initialized *globally*.
            self.__class__._initialized = True
            print("Telemetry Singleton: Initialization complete.")  # Added print
            return self
        except Exception as e:
            # Catch any exception during setup, format with traceback, and re-raise.
            tb = traceback.format_exc()
            self._logger.exception(
                f"Failed to initialize telemetry: {e}\n{tb}"
            )  # Log the error
            # Potentially set initialized to False or handle differently depending on desired recovery.
            self.__class__._initialized = False  # Ensure we know init failed
            raise RuntimeError(f"Failed to initialize telemetry: {e}\n{tb}") from e

    # What: Property to check if telemetry has been successfully initialized.
    @property
    def initialized(self) -> bool:
        """Returns True if telemetry has been successfully initialized."""
        return self.__class__._initialized

    # What: Setter for the initialized flag (less common to use externally).
    @initialized.setter
    def initialized(self, value: bool) -> None:
        """Sets the global initialized flag (use with caution)."""
        # Allows manually marking as uninitialized, e.g., during reset.
        self.__class__._initialized = value

    # What: Class method providing an alternative way to get/create the instance.
    # Why: Explicitly shows intent of creating from settings. Equivalent to `Telemetry(settings)`.
    @classmethod
    def from_settings(cls: type[Telemetry], settings: TelemetrySettings) -> Telemetry:
        """Creates or retrieves the singleton Telemetry instance configured with settings."""
        return cls(settings)

    # What: Class method to retrieve the existing singleton instance *without* providing settings again.
    # Why: Allows accessing the already initialized singleton from other parts of the code.
    # Raises: `ValueError` if called before the singleton has been initialized with settings.
    @classmethod
    def get_instance(cls: type[Telemetry]) -> Telemetry:
        """Retrieves the initialized singleton instance."""
        if cls._instance is None:
            # Attempt re-initialization only if settings were stored previously.
            # This handles cases where instance is None but settings might exist (e.g., after reset).
            if cls._settings is not None:
                print(
                    "Telemetry Singleton: Instance is None, but settings exist. Re-initializing."
                )  # Added print
                with cls._lock:  # Need lock for re-initialization attempt
                    # Re-check instance inside lock
                    if cls._instance is None:
                        cls.from_settings(cls._settings)  # Re-run initialization
                    # If instance is still None after from_settings, something went wrong.
                    if cls._instance is None:
                        raise RuntimeError("Telemetry re-initialization failed.")
            else:
                # If instance is None and settings are None, it was never initialized.
                raise ValueError(
                    "Telemetry has not been initialized with settings. Call Telemetry(settings) first."
                )

        # If instance exists (either originally or after re-init), return it.
        return cls._instance

    # What: Class method to reset the singleton state.
    # Why: Useful primarily for testing or scenarios requiring reconfiguration.
    #      Allows the singleton to be garbage collected (if no other references exist)
    #      and re-initialized with potentially new settings later.
    @classmethod
    def reset(cls: type[Telemetry]) -> None:
        """Resets the singleton instance, allowing re-initialization."""
        print("Telemetry Singleton: Resetting...")  # Added print
        with cls._lock:
            if cls._instance is not None:
                # Ensure components are shut down before discarding the instance.
                try:
                    cls._instance.shutdown()
                except Exception as e:
                    print(f"Telemetry Singleton: Error during shutdown in reset: {e}")
                cls._instance = None
            # Reset global flags
            cls._initialized = False
            cls._settings = None  # Clear stored settings too
            print("Telemetry Singleton: Reset complete.")  # Added print

    # What: Instance method to trigger shutdown of all telemetry components.
    def shutdown(self) -> None:
        """Shuts down all underlying telemetry components."""
        # Check if components were successfully created during initialization.
        if self.components:
            self.components.shutdown_all()
        else:
            print(
                "Telemetry Singleton: Shutdown called, but components were not initialized."
            )  # Added print
        # Mark as uninitialized after shutdown.
        self.initialized = False

    # --- Facade Accessor Properties ---
    # What: Properties providing convenient access to the underlying OTel Tracer, Meter, etc.
    # Why: The Facade pattern simplifies interaction. Users call `telemetry.tracer`
    #      instead of needing to know about `telemetry.components.tracing.tracer`.
    # How it works: Returns the specific object from the `components` container, or None/No-Op
    #              if telemetry isn't initialized or the component doesn't exist.

    @property
    def tracer(self) -> trace.Tracer | None:
        """Get the configured OpenTelemetry tracer, or None if not initialized."""
        if not self.initialized or not self.components:
            self._logger.warning(
                "Attempted to get tracer, but telemetry is not initialized."
            )
            return None  # Or return NoOpTracer() if preferred non-None return
        return self.components.tracing.tracer

    @property
    def meter(self) -> metrics.Meter | None:
        """Get the configured OpenTelemetry meter, or None if not initialized."""
        if not self.initialized or not self.components:
            self._logger.warning(
                "Attempted to get meter, but telemetry is not initialized."
            )
            return None  # Or return NoOpMeter()
        return self.components.metrics.meter

    @property
    def propagator(self) -> TextMapPropagator | None:
        """Get the configured OpenTelemetry text map propagator, or None if not initialized."""
        if not self.initialized or not self.components:
            self._logger.warning(
                "Attempted to get propagator, but telemetry is not initialized."
            )
            return None  # Propagators don't have a standard NoOp equivalent
        return self.components.propagator.propagator

    @property
    def logger(self) -> logging.Logger:
        """Get the trace-aware standard Python logger."""
        # Returns the component's logger if initialized, otherwise a default logger.
        if not self.initialized or not self.components:
            # Log a warning if accessed before init, but still return *a* logger.
            # self._logger.warning("Attempted to get logger, but telemetry is not initialized. Returning default logger.")
            # Return a logger named after *this* module if not initialized.
            return logging.getLogger(__name__)  # Fallback logger
        # Return the logger configured by LoggingComponent
        return self.components.logging.logger

    # --- Convenience Methods ---

    # What: A context manager simplifying the creation of spans.
    # Why: Provides a `with` statement syntax for starting and automatically ending spans,
    #      handling exceptions, and setting status. Wraps `tracer.start_as_current_span`.
    # Parameters: Mirrors the parameters of `tracer.start_as_current_span`.
    # Returns: A generator yielding the created `trace.Span`.
    @contextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Context | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Attributes | None = None,
        links: _Links | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
        end_on_exit: bool = True,
    ) -> collections.abc.Generator[trace.Span, None, None]:
        """Starts a new span as the current span in context.

        Args:
            name: The name of the span.
            context: The parent context (optional).
            kind: The span kind (e.g., SERVER, CLIENT, INTERNAL).
            attributes: Initial attributes for the span.
            links: Links to other spans.
            start_time: Explicit start timestamp (ns).
            record_exception: Record exceptions details on the span.
            set_status_on_exception: Set span status to ERROR on unhandled exceptions.
            end_on_exit: Automatically end the span when exiting the context manager.

        Yields:
            The newly created span.
        """
        _tracer = self.tracer  # Get the tracer property
        if _tracer is None:  # Check if initialized
            # What: Fallback behavior if tracing is not initialized.
            # Why: Prevents crashes, allows code using this method to run even if
            #      telemetry setup failed or was disabled.
            # How it works: Uses the OTel NoOpTracer to create a No-Op span which does nothing.
            self._logger.warning(
                f"Cannot start span '{name}', tracer not available. Using NoOp span."
            )
            # Return a no-op span if telemetry is not set up
            with NoOpTracer().start_as_current_span(name) as span:
                yield span
            return  # Exit the generator

        # What: Delegate the actual span creation to the configured OTel tracer.
        with _tracer.start_as_current_span(
            name=name,  # Corrected parameter name
            context=context,
            kind=kind,
            attributes=attributes,
            links=links,
            start_time=start_time,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
            end_on_exit=end_on_exit,
        ) as span:
            # Yield the real span to the caller within the 'with' block.
            yield span

    # What: Convenience methods for creating metric instruments (Counter, Histogram, etc.).
    # Why: Simplifies instrument creation by checking for initialization and providing No-Op
    #      fallbacks, preventing errors if metrics are disabled or uninitialized.
    # How it works: Checks `self.initialized` and `self.meter`. If available, delegates to
    #              `self.meter.create_...`. Otherwise, creates and returns a No-Op instrument.

    def create_counter(
        self,
        name: str,
        description: str = "",  # Added default empty string
        unit: str = "1",
    ) -> metrics.Counter:
        """Creates a Counter metric instrument, or a NoOpCounter if not initialized."""
        _meter = self.meter
        if _meter is None:  # Check if initialized via property access
            self._logger.warning(
                f"Cannot create counter '{name}', meter not available. Using NoOp counter."
            )
            # Return a no-op counter if telemetry is not set up
            return NoOpMeter(name="no-op-meter").create_counter(
                name, description=description, unit=unit
            )
        return _meter.create_counter(
            name, unit=unit, description=description
        )  # Correct param order

    def create_histogram(
        self,
        name: str,
        description: str = "",  # Added default
        unit: str = "1",
    ) -> metrics.Histogram:
        """Creates a Histogram metric instrument, or a NoOpHistogram if not initialized."""
        _meter = self.meter
        if _meter is None:
            self._logger.warning(
                f"Cannot create histogram '{name}', meter not available. Using NoOp histogram."
            )
            # Return a no-op histogram if telemetry is not set up
            return NoOpMeter(name="no-op-meter").create_histogram(
                name, description=description, unit=unit
            )

        return _meter.create_histogram(
            name, unit=unit, description=description
        )  # Correct param order

    def create_up_down_counter(
        self,
        name: str,
        description: str = "",  # Added default
        unit: str = "1",
    ) -> metrics.UpDownCounter:
        """Creates an UpDownCounter metric instrument, or a NoOpUpDownCounter if not initialized."""
        _meter = self.meter
        if _meter is None:
            self._logger.warning(
                f"Cannot create up_down_counter '{name}', meter not available. Using NoOp up_down_counter."
            )
            # Return a no-op up-down counter if telemetry is not set up
            return NoOpMeter(name="no-op-meter").create_up_down_counter(
                name, description=description, unit=unit
            )

        return _meter.create_up_down_counter(
            name, unit=unit, description=description
        )  # Correct param order

    # What: Convenience method for logging.
    # Why: Provides a single method in the facade to log messages using the
    #      trace-aware logger configured during setup.
    # How it works: Delegates to the `log` method of the logger obtained from `self.logger`.
    def log(
        self,
        level: int,  # Use standard logging level integers (e.g., logging.INFO)
        message: str,
        extra: (
            dict[str, object] | None
        ) = None,  # For passing additional structured data
    ) -> None:
        """Log a message using the trace-aware logger."""
        # Note: The self.logger property already handles initialization checks.
        # The LoggingInstrumentor ensures trace context is added if available.
        self.logger.log(level, message, extra=extra)

    # What: Convenience method to inject propagation context into a carrier.
    # Why: Simplifies context injection using the globally configured propagator.
    # How it works: Delegates to the `inject` method of the propagator obtained from `self.propagator`.
    def inject_context(self, carrier: dict[str, str]) -> None:
        """Injects the current context into a carrier dict using the configured propagator."""
        _propagator = self.propagator
        if _propagator:
            try:
                _propagator.inject(carrier)
            except Exception as e:
                self.logger.error(f"Failed to inject context: {e}", exc_info=True)
        else:
            self.logger.warning("Cannot inject context, propagator not available.")

    # What: Convenience method to extract propagation context from a carrier.
    # Why: Simplifies context extraction using the globally configured propagator.
    # How it works: Delegates to the `extract` method of the propagator. Returns the new Context object.
    def extract_context(
        self, carrier: dict[str, str]
    ) -> Context | None:  # Return Context or None
        """Extracts context from a carrier dict using the configured propagator."""
        _propagator = self.propagator
        if _propagator:
            try:
                return _propagator.extract(carrier)
            except Exception as e:
                self.logger.error(f"Failed to extract context: {e}", exc_info=True)
                return None  # Return None on error
        else:
            self.logger.warning("Cannot extract context, propagator not available.")
            return None  # Return None if not available

    # --- @traced Decorator ---
    # What: Defines a decorator `@traced` to automatically wrap function calls in spans.
    # Why: Reduces boilerplate code for tracing common function executions.
    # How it works:
    #   - Uses `@overload` to provide distinct type hints for decorating synchronous vs.
    #     asynchronous functions, ensuring type safety for awaitables.
    #   - The main implementation inspects the function (`iscoroutinefunction`) to determine
    #     if it's async.
    #   - It creates a wrapper function (`sync_wrapper` or `async_wrapper`).
    #   - Inside the wrapper, it checks if telemetry is initialized. If not, it calls the
    #     original function directly.
    #   - If initialized, it uses `self.start_as_current_span` to create a span around the
    #     call to the original function.
    #   - It automatically sets the span name (using function qualified name if not provided).
    #   - It handles exceptions, setting the span status to ERROR and recording the exception.
    #   - Uses `functools.wraps` to preserve the original function's metadata.
    #   - Uses `cast` to satisfy the type checker regarding the return type of the wrapper.

    @overload
    def traced(
        self,
        span_name: str | None = None,  # Optional custom span name
        attributes: Attributes | None = None,  # Optional span attributes
        kind: SpanKind = SpanKind.INTERNAL,  # Default span kind
    ) -> Callable[  # Decorator for async functions
        [Callable[P, Awaitable[AsyncR]]],  # Takes an async func P -> Awaitable[AsyncR]
        Callable[P, Awaitable[AsyncR]],  # Returns an async func P -> Awaitable[AsyncR]
    ]: ...

    @overload
    def traced(
        self,
        span_name: str | None = None,
        attributes: Attributes | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
    ) -> Callable[  # Decorator for sync functions
        [Callable[P, R]],  # Takes a sync func P -> R
        Callable[P, R],  # Returns a sync func P -> R
    ]: ...

    # Actual implementation handling both sync and async
    def traced(
        self,
        span_name: str | None = None,
        attributes: Attributes | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
    ) -> Callable[[Callable[P, Any]], Callable[P, Any]]:  # General internal signature
        """Decorator to automatically wrap function calls in an OpenTelemetry span."""

        def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
            # Determine span name: use provided name or generate from function module/name.
            name = span_name or f"{func.__module__}.{func.__qualname__}"

            # Check if the decorated function is async.
            is_async = inspect.iscoroutinefunction(func)

            if is_async:
                # --- Wrapper for ASYNC functions ---
                @functools.wraps(func)  # Preserve original function metadata
                async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncR:
                    # Check if tracing is active before creating span.
                    _tracer = self.tracer
                    if _tracer is None:  # Use property which checks initialization
                        # If not initialized, just run the original async function.
                        return await func(*args, **kwargs)  # type: ignore[no-any-return]

                    # If initialized, start span using the context manager.
                    with self.start_as_current_span(
                        name=name,  # Use determined span name
                        kind=kind,
                        attributes=attributes,
                    ) as span:  # Get the span object
                        try:
                            # Await the original async function within the span context.
                            result = await func(*args, **kwargs)  # type: ignore[no-any-return]
                            # Span status is OK by default if no exception.
                            return result
                        except Exception as e:
                            # If an exception occurs:
                            # Set span status to Error.
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )  # Add description
                            # Record exception details on the span.
                            span.record_exception(e)
                            # Re-raise the exception to maintain original program flow.
                            raise

                # Return the async wrapper, cast for type checker.
                return cast(Callable[P, Awaitable[AsyncR]], async_wrapper)
            else:
                # --- Wrapper for SYNC functions ---
                @functools.wraps(func)  # Preserve original function metadata
                def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                    # Check if tracing is active.
                    _tracer = self.tracer
                    if _tracer is None:
                        # If not initialized, just run the original sync function.
                        return func(*args, **kwargs)  # type: ignore[no-any-return]

                    # If initialized, start span using the context manager.
                    with self.start_as_current_span(
                        name=name,
                        kind=kind,
                        attributes=attributes,
                    ) as span:
                        try:
                            # Call the original sync function within the span context.
                            result = func(*args, **kwargs)  # type: ignore[no-any-return]
                            # Span status OK by default.
                            return result
                        except Exception as e:
                            # Handle exceptions similarly to the async wrapper.
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                            span.record_exception(e)
                            raise

                # Return the sync wrapper, cast for type checker.
                return cast(Callable[P, R], sync_wrapper)

        # Return the 'decorator' function itself (which takes 'func' and returns a 'wrapper').
        return decorator
