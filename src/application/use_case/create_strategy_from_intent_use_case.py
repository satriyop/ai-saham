"""
CreateStrategyFromIntent use case - translate natural language to strategy YAML.

Orchestrates AI-powered translation of natural language strategy descriptions
into validated YAML configurations that can be used with the strategy system.

Layer: Application
Depends on: StrategyTranslator port, RulesLoader port, IndicatorRegistry
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.ports.rules_loader import RulesLoader
from src.application.ports.strategy_translator import (
    StrategyTranslator,
    StrategyTranslatorAuthError,
    StrategyTranslatorError,
    StrategyTranslatorRateLimitError,
    StrategyTranslatorTimeoutError,
)
from src.application.rules.exceptions import (
    RulesError,
    RulesSchemaError,
    RulesValidationError,
)

if TYPE_CHECKING:
    from src.application.rules.schema import RuleSet
    from src.application.services.indicator_registry import IndicatorRegistry


@dataclass
class CreateStrategyFromIntentRequest:
    """Request DTO for strategy creation from natural language.

    Attributes:
        intent: Natural language description of the strategy.
                E.g., "buy when RSI below 30 and EMA crossover"
        strategy_name: Name for the generated strategy.
    """

    intent: str
    strategy_name: str


@dataclass
class CreateStrategyFromIntentResponse:
    """Response DTO containing translation result.

    Attributes:
        intent: The original intent that was translated.
        yaml_content: The generated YAML string (None if failed/unsupported).
        rule_set: The parsed RuleSet (None if failed/unsupported).
        strategy_name: The strategy name.
        success: True if translation succeeded.
        unsupported: True if intent cannot be expressed as a strategy.
        error_message: Error description (None if successful or unsupported).
        provider: The AI provider used for translation.
    """

    intent: str
    yaml_content: str | None
    rule_set: "RuleSet | None"
    strategy_name: str
    success: bool
    unsupported: bool
    error_message: str | None = None
    provider: str = "unknown"

    @classmethod
    def success_response(
        cls,
        intent: str,
        yaml_content: str,
        rule_set: "RuleSet",
        strategy_name: str,
        provider: str,
    ) -> "CreateStrategyFromIntentResponse":
        """Create a successful response.

        Args:
            intent: The original intent.
            yaml_content: The generated YAML string.
            rule_set: The parsed and validated RuleSet.
            strategy_name: The strategy name.
            provider: The AI provider used.

        Returns:
            A successful response with YAML and RuleSet.
        """
        return cls(
            intent=intent,
            yaml_content=yaml_content,
            rule_set=rule_set,
            strategy_name=strategy_name,
            success=True,
            unsupported=False,
            error_message=None,
            provider=provider,
        )

    @classmethod
    def unsupported_response(
        cls,
        intent: str,
        strategy_name: str,
        provider: str,
    ) -> "CreateStrategyFromIntentResponse":
        """Create an unsupported response.

        Used when the intent cannot be expressed as a strategy.

        Args:
            intent: The original intent.
            strategy_name: The requested strategy name.
            provider: The AI provider used.

        Returns:
            An unsupported response.
        """
        return cls(
            intent=intent,
            yaml_content=None,
            rule_set=None,
            strategy_name=strategy_name,
            success=False,
            unsupported=True,
            error_message=None,
            provider=provider,
        )

    @classmethod
    def error_response(
        cls,
        intent: str,
        strategy_name: str,
        error_message: str,
        provider: str,
    ) -> "CreateStrategyFromIntentResponse":
        """Create an error response.

        Args:
            intent: The original intent.
            strategy_name: The requested strategy name.
            error_message: Description of what went wrong.
            provider: The AI provider used.

        Returns:
            An error response.
        """
        return cls(
            intent=intent,
            yaml_content=None,
            rule_set=None,
            strategy_name=strategy_name,
            success=False,
            unsupported=False,
            error_message=error_message,
            provider=provider,
        )


class CreateStrategyFromIntentUseCase:
    """
    Use case for translating natural language into validated strategy YAML.

    This use case:
        1. Validates the input intent
        2. Gets available indicators from the registry
        3. Calls the StrategyTranslator to get YAML content
        4. Parses and validates the YAML using the injected RulesLoader
        5. Returns the validated YAML and RuleSet

    Important:
        - All errors are caught and returned as responses (no exceptions)
        - UNSUPPORTED is a valid response (not an error)
        - The YAML is validated before being returned

    Example (adapter/composition-root wiring):
        translator = StrategyTranslatorAdapter(provider="mock")
        registry = create_indicator_registry()
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
            rules_loader=rules_loader,  # RulesLoader impl injected by the adapter
        )
        response = use_case.execute(CreateStrategyFromIntentRequest(
            intent="RSI oversold strategy",
            strategy_name="rsi_oversold",
        ))

        if response.success:
            print(f"YAML:\\n{response.yaml_content}")
            # Save to file or register
        elif response.unsupported:
            print("This intent cannot be expressed as a strategy")
        else:
            print(f"Error: {response.error_message}")
    """

    def __init__(
        self,
        translator: StrategyTranslator,
        registry: "IndicatorRegistry",
        rules_loader: RulesLoader,
    ) -> None:
        """
        Initialize with translator, indicator registry, and rules loader.

        Args:
            translator: StrategyTranslator adapter for AI translation.
            registry: IndicatorRegistry for getting available indicators
                     and validating generated YAML.
            rules_loader: RulesLoader port interface. Must be injected by the
                caller's adapter/composition root with a concrete
                implementation from the infrastructure layer.
        """
        self._translator = translator
        self._registry = registry
        self._rules_loader = rules_loader

    def execute(
        self, request: CreateStrategyFromIntentRequest
    ) -> CreateStrategyFromIntentResponse:
        """
        Translate natural language intent into a validated strategy.

        This method catches all errors and returns them as responses
        rather than raising exceptions. This allows graceful degradation
        when AI translation fails.

        Args:
            request: Contains intent and strategy name.

        Returns:
            CreateStrategyFromIntentResponse with YAML/RuleSet or error/unsupported.
        """
        provider = self._get_provider_name()
        strategy_name = request.strategy_name.strip()

        # Validate input
        intent = request.intent.strip()
        if not intent:
            return CreateStrategyFromIntentResponse.error_response(
                intent=request.intent,
                strategy_name=strategy_name,
                error_message="Intent cannot be empty",
                provider=provider,
            )

        if not strategy_name:
            return CreateStrategyFromIntentResponse.error_response(
                intent=intent,
                strategy_name=request.strategy_name,
                error_message="Strategy name cannot be empty",
                provider=provider,
            )

        try:
            # Step 1: Get available indicators from registry
            available_indicators = self._registry.get_available_indicators()

            # Step 2: Translate intent to YAML
            yaml_content = self._translator.translate(
                intent=intent,
                strategy_name=strategy_name,
                available_indicators=available_indicators,
            )

            # Step 3: Check for UNSUPPORTED
            if yaml_content == "UNSUPPORTED":
                return CreateStrategyFromIntentResponse.unsupported_response(
                    intent=intent,
                    strategy_name=strategy_name,
                    provider=provider,
                )

            # Step 4: Validate YAML by parsing it
            try:
                rule_set = self._rules_loader.load_from_string(
                    content=yaml_content,
                    registry=self._registry,
                    source_name=f"<generated:{strategy_name}>",
                )
            except RulesSchemaError as e:
                return CreateStrategyFromIntentResponse.error_response(
                    intent=intent,
                    strategy_name=strategy_name,
                    error_message=f"Generated invalid YAML schema: {e}",
                    provider=provider,
                )
            except RulesValidationError as e:
                return CreateStrategyFromIntentResponse.error_response(
                    intent=intent,
                    strategy_name=strategy_name,
                    error_message=f"Generated invalid strategy: {e}",
                    provider=provider,
                )
            except RulesError as e:
                return CreateStrategyFromIntentResponse.error_response(
                    intent=intent,
                    strategy_name=strategy_name,
                    error_message=f"YAML validation error: {e}",
                    provider=provider,
                )

            # Step 5: Success
            return CreateStrategyFromIntentResponse.success_response(
                intent=intent,
                yaml_content=yaml_content,
                rule_set=rule_set,
                strategy_name=rule_set.name,
                provider=provider,
            )

        except StrategyTranslatorAuthError as e:
            return CreateStrategyFromIntentResponse.error_response(
                intent=intent,
                strategy_name=strategy_name,
                error_message=str(e),
                provider=provider,
            )

        except StrategyTranslatorTimeoutError:
            return CreateStrategyFromIntentResponse.error_response(
                intent=intent,
                strategy_name=strategy_name,
                error_message="AI translation timed out",
                provider=provider,
            )

        except StrategyTranslatorRateLimitError as e:
            return CreateStrategyFromIntentResponse.error_response(
                intent=intent,
                strategy_name=strategy_name,
                error_message=str(e),
                provider=provider,
            )

        except StrategyTranslatorError as e:
            return CreateStrategyFromIntentResponse.error_response(
                intent=intent,
                strategy_name=strategy_name,
                error_message=str(e),
                provider=provider,
            )

        except Exception as e:
            # Catch-all for unexpected errors
            return CreateStrategyFromIntentResponse.error_response(
                intent=intent,
                strategy_name=strategy_name,
                error_message=f"Unexpected error: {e}",
                provider=provider,
            )

    def _get_provider_name(self) -> str:
        """Get provider name from translator."""
        if hasattr(self._translator, "provider_name"):
            return self._translator.provider_name
        return "unknown"
