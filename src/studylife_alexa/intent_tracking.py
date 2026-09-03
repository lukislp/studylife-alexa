"""Wires studylife_alexa_intents_total (metrics.py) into the ask-sdk dispatch cycle
without touching any of the 18 individual request-handler classes in handlers.py.

Two global interceptors (registered onto the SkillBuilder in skill.py) plus this
module's own request-name extraction, shared with handlers.py's
CatchAllExceptionHandler - the one place that DOES need its own instrumentation,
since RequestDispatcher.dispatch() (ask_sdk_runtime/dispatch.py) only runs the global
response interceptors after a handler returns successfully; a handler that raises goes
straight to the exception mapper, skipping response interceptors entirely. See that
class's own comment in handlers.py.
"""

from __future__ import annotations

from ask_sdk_core.dispatch_components import AbstractRequestInterceptor, AbstractResponseInterceptor
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response

from studylife_alexa.metrics import INTENTS_TOTAL

# Key into HandlerInput.attributes_manager.request_attributes (a plain dict, fresh per
# incoming request - not shared session/persistent attributes) - lets the response
# interceptor and CatchAllExceptionHandler recover the same name the request
# interceptor already extracted, instead of re-deriving it.
_REQUEST_ATTRIBUTE_KEY = "_studylife_alexa_metrics_intent_name"


def request_name(handler_input: HandlerInput) -> str:
    """The bounded intent/request name for a given request: the request's own
    object_type (e.g. "LaunchRequest", "SessionEndedRequest") for anything that isn't
    an IntentRequest, or the wrapped intent's name (e.g. "CoursesIntent",
    "AMAZON.HelpIntent") when it is one. Never user utterance text or slot values -
    both are unbounded, unlike this set (see skill.py's registered handlers)."""
    request = handler_input.request_envelope.request
    if request.object_type == "IntentRequest":
        return request.intent.name
    return request.object_type


class MetricsRequestInterceptor(AbstractRequestInterceptor):
    """Runs before dispatch - stashes this request's name so the response
    interceptor and CatchAllExceptionHandler can label their outcome without
    re-deriving it themselves."""

    def process(self, handler_input: HandlerInput) -> None:
        handler_input.attributes_manager.request_attributes[_REQUEST_ATTRIBUTE_KEY] = request_name(
            handler_input
        )


class MetricsResponseInterceptor(AbstractResponseInterceptor):
    """Runs after a handler returns successfully - records outcome="ok". The error
    path is recorded separately, by CatchAllExceptionHandler (see this module's own
    docstring for why)."""

    def process(self, handler_input: HandlerInput, response: Response) -> None:
        intent = handler_input.attributes_manager.request_attributes.get(
            _REQUEST_ATTRIBUTE_KEY
        ) or request_name(handler_input)
        INTENTS_TOTAL.labels(intent=intent, outcome="ok").inc()


def record_intent_error(handler_input: HandlerInput) -> None:
    """Called from CatchAllExceptionHandler - see this module's own docstring for why
    that's the one handler that has to record its own outcome."""
    intent = handler_input.attributes_manager.request_attributes.get(
        _REQUEST_ATTRIBUTE_KEY
    ) or request_name(handler_input)
    INTENTS_TOTAL.labels(intent=intent, outcome="error").inc()
