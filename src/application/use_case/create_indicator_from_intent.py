"""
CreateIndicatorFromIntent use case - translate natural language to formula.

Orchestrates AI-powered translation of natural language indicator descriptions
into validated formula strings that can be registered with the indicator registry.

Layer: Application
Depends on: FormulaTranslator port, Formula parser/validator
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.formula.exceptions import FormulaError, FormulaValidationError
from src.application.formula.parser import parse
from src.application.formula.validator import validate_formula_references
from src.application.ports.formula_translator import (
    FormulaTranslator,
    FormulaTranslatorError,
    TranslatorAuthError,
    TranslatorRateLimitError,
    TranslatorTimeoutError,
)
from src.infrastructure.ai.formula_translator_prompt import DEFAULT_SERIES

if TYPE_CHECKING:
    from src.application.formula.ast_nodes import ASTNode


@dataclass
class CreateIndicatorFromIntentRequest:
    """Request DTO for indicator creation from natural language.

    Attributes:
        intent: Natural language description of the indicator.
                E.g., "smoothed RSI with 14-period and 10-day smoothing"
        indicator_name: Optional name for the indicator. If not provided,
                       a name can be generated from the formula.
    """

    intent: str
    indicator_name: str | None = None


@dataclass
class CreateIndicatorFromIntentResponse:
    """Response DTO containing translation result.

    Attributes:
        intent: The original intent that was translated.
        formula: The translated formula string (None if failed/unsupported).
        ast: The parsed AST (None if failed/unsupported).
        indicator_name: The indicator name (None if not provided).
        success: True if translation succeeded.
        unsupported: True if intent cannot be expressed as a formula.
        error_message: Error description (None if successful or unsupported).
        provider: The AI provider used for translation.
    """

    intent: str
    formula: str | None
    ast: "ASTNode | None"
    indicator_name: str | None
    success: bool
    unsupported: bool
    error_message: str | None = None
    provider: str = "unknown"

    @classmethod
    def success_response(
        cls,
        intent: str,
        formula: str,
        ast: "ASTNode",
        indicator_name: str | None,
        provider: str,
    ) -> "CreateIndicatorFromIntentResponse":
        """Create a successful response.

        Args:
            intent: The original intent.
            formula: The translated formula string.
            ast: The parsed AST.
            indicator_name: The indicator name (if provided).
            provider: The AI provider used.

        Returns:
            A successful response with formula and AST.
        """
        return cls(
            intent=intent,
            formula=formula,
            ast=ast,
            indicator_name=indicator_name,
            success=True,
            unsupported=False,
            error_message=None,
            provider=provider,
        )

    @classmethod
    def unsupported_response(
        cls,
        intent: str,
        provider: str,
    ) -> "CreateIndicatorFromIntentResponse":
        """Create an unsupported response.

        Used when the intent cannot be expressed as a formula.

        Args:
            intent: The original intent.
            provider: The AI provider used.

        Returns:
            An unsupported response.
        """
        return cls(
            intent=intent,
            formula=None,
            ast=None,
            indicator_name=None,
            success=False,
            unsupported=True,
            error_message=None,
            provider=provider,
        )

    @classmethod
    def error_response(
        cls,
        intent: str,
        error_message: str,
        provider: str,
    ) -> "CreateIndicatorFromIntentResponse":
        """Create an error response.

        Args:
            intent: The original intent.
            error_message: Description of what went wrong.
            provider: The AI provider used.

        Returns:
            An error response.
        """
        return cls(
            intent=intent,
            formula=None,
            ast=None,
            indicator_name=None,
            success=False,
            unsupported=False,
            error_message=error_message,
            provider=provider,
        )


class CreateIndicatorFromIntentUseCase:
    """
    Use case for translating natural language into validated formulas.

    This use case:
        1. Validates the input intent
        2. Calls the FormulaTranslator to get a formula string
        3. Parses the formula to validate syntax
        4. Validates that all referenced indicators are available
        5. Returns the validated formula and AST

    Important:
        - All errors are caught and returned as responses (no exceptions)
        - UNSUPPORTED is a valid response (not an error)
        - The formula is validated before being returned

    Example:
        translator = FormulaTranslatorAdapter(provider="mock")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions={"SMA", "EMA", "RSI"},
        )
        response = use_case.execute(CreateIndicatorFromIntentRequest(
            intent="smoothed RSI with 14-period and 10-day smoothing"
        ))

        if response.success:
            print(f"Formula: {response.formula}")
            # Register: registry.register_formula("SMOOTH_RSI", response.ast)
        elif response.unsupported:
            print("This intent cannot be expressed as a formula")
        else:
            print(f"Error: {response.error_message}")
    """

    def __init__(
        self,
        translator: FormulaTranslator,
        available_functions: set[str],
        available_series: set[str] | None = None,
    ) -> None:
        """
        Initialize with translator and available indicator configuration.

        Args:
            translator: FormulaTranslator adapter for AI translation.
            available_functions: Set of available function names (uppercase).
                               E.g., {"SMA", "EMA", "RSI", "ATR"}
            available_series: Set of available series names. If None, uses
                            {"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"}.
        """
        self._translator = translator
        self._available_functions = available_functions
        self._available_series = available_series or set(DEFAULT_SERIES)

    def execute(
        self, request: CreateIndicatorFromIntentRequest
    ) -> CreateIndicatorFromIntentResponse:
        """
        Translate natural language intent into a validated formula.

        This method catches all errors and returns them as responses
        rather than raising exceptions. This allows graceful degradation
        when AI translation fails.

        Args:
            request: Contains intent and optional indicator name.

        Returns:
            CreateIndicatorFromIntentResponse with formula/AST or error/unsupported.
        """
        provider = self._get_provider_name()

        # Validate input
        intent = request.intent.strip()
        if not intent:
            return CreateIndicatorFromIntentResponse.error_response(
                intent=request.intent,
                error_message="Intent cannot be empty",
                provider=provider,
            )

        try:
            # Step 1: Translate intent to formula string
            formula = self._translator.translate(
                intent=intent,
                available_functions=self._available_functions,
                available_series=self._available_series,
            )

            # Step 2: Check for UNSUPPORTED
            if formula == "UNSUPPORTED":
                return CreateIndicatorFromIntentResponse.unsupported_response(
                    intent=intent,
                    provider=provider,
                )

            # Step 3: Parse formula to validate syntax
            try:
                ast = parse(formula)
            except FormulaError as e:
                return CreateIndicatorFromIntentResponse.error_response(
                    intent=intent,
                    error_message=f"Invalid formula syntax: {e}",
                    provider=provider,
                )

            # Step 4: Validate references
            try:
                validate_formula_references(ast, self._available_functions)
            except FormulaValidationError as e:
                return CreateIndicatorFromIntentResponse.error_response(
                    intent=intent,
                    error_message=f"Formula validation failed: {e}",
                    provider=provider,
                )

            # Step 5: Success
            return CreateIndicatorFromIntentResponse.success_response(
                intent=intent,
                formula=formula,
                ast=ast,
                indicator_name=request.indicator_name,
                provider=provider,
            )

        except TranslatorAuthError as e:
            return CreateIndicatorFromIntentResponse.error_response(
                intent=intent,
                error_message=str(e),
                provider=provider,
            )

        except TranslatorTimeoutError:
            return CreateIndicatorFromIntentResponse.error_response(
                intent=intent,
                error_message="AI translation timed out",
                provider=provider,
            )

        except TranslatorRateLimitError as e:
            return CreateIndicatorFromIntentResponse.error_response(
                intent=intent,
                error_message=str(e),
                provider=provider,
            )

        except FormulaTranslatorError as e:
            return CreateIndicatorFromIntentResponse.error_response(
                intent=intent,
                error_message=str(e),
                provider=provider,
            )

        except Exception as e:
            # Catch-all for unexpected errors
            return CreateIndicatorFromIntentResponse.error_response(
                intent=intent,
                error_message=f"Unexpected error: {e}",
                provider=provider,
            )

    def _get_provider_name(self) -> str:
        """Get provider name from translator."""
        if hasattr(self._translator, "provider_name"):
            return self._translator.provider_name
        return "unknown"
