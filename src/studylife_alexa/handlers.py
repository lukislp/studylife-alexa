"""Request handlers for the StudyLife Alexa skill.

TestIntentHandler is Phase-A scaffolding (canned response, proved out the endpoint/
signature-verification/deployment pipeline before any real functionality existed) -
kept around as a no-account-needed connectivity check. CoursesIntentHandler is the
first real StudyLife-backed intent, proving account linking end to end.
"""

from __future__ import annotations

from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import get_account_linking_access_token, is_intent_name, is_request_type
from ask_sdk_model import Response
from ask_sdk_model.ui import LinkAccountCard

from studylife_alexa.client import StudyLifeApiError, list_courses_sync
from studylife_alexa.config import Settings
from studylife_alexa.oauth_store import load_access_token_sync


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = "Willkommen bei Study Life. Sag zum Testen einfach: sag hallo."
        return handler_input.response_builder.speak(speech).ask(speech).response


class TestIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("TestIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = "Verbindung funktioniert. Study Life ist bereit."
        return handler_input.response_builder.speak(speech).response


class CoursesIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("CoursesIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        alexa_access_token = get_account_linking_access_token(handler_input)
        if alexa_access_token is None:
            speech = (
                "Dafür muss dein StudyLife-Konto erst verknüpft werden. "
                "Ich habe dir dazu einen Link in der Alexa-App geschickt."
            )
            return (
                handler_input.response_builder.speak(speech)
                .set_card(LinkAccountCard())
                .set_should_end_session(True)
                .response
            )

        settings = Settings()  # type: ignore[call-arg]
        api_key = load_access_token_sync(
            settings.alexa_oauth_db_path,
            settings.alexa_token_encryption_key or "",
            alexa_access_token,
        )
        if api_key is None:
            speech = (
                "Deine Verknüpfung ist abgelaufen. Bitte verbinde dein StudyLife-Konto "
                "in der Alexa-App erneut."
            )
            return (
                handler_input.response_builder.speak(speech)
                .set_card(LinkAccountCard())
                .set_should_end_session(True)
                .response
            )

        try:
            courses = list_courses_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            speech = "StudyLife konnte gerade nicht erreicht werden. Versuch es später noch mal."
            return handler_input.response_builder.speak(speech).response

        if not courses:
            speech = "Du hast aktuell keine Kurse in StudyLife angelegt."
        else:
            speech = f"Du hast aktuell {len(courses)} Kurse in StudyLife."
        return handler_input.response_builder.speak(speech).response


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = "Sag zum Testen: sag hallo."
        return handler_input.response_builder.speak(speech).ask(speech).response


class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.CancelIntent")(handler_input) or is_intent_name(
            "AMAZON.StopIntent"
        )(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return (
            handler_input.response_builder.speak("Bis bald.").set_should_end_session(True).response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        # Alexa ignores any response body for SessionEndedRequest - nothing to build.
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        speech = "Entschuldigung, da ist etwas schiefgelaufen."
        return handler_input.response_builder.speak(speech).response
