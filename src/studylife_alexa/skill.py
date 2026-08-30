from ask_sdk_core.skill_builder import SkillBuilder

from studylife_alexa.config import Settings
from studylife_alexa.handlers import (
    CancelOrStopIntentHandler,
    CatchAllExceptionHandler,
    HelpIntentHandler,
    LaunchRequestHandler,
    SessionEndedRequestHandler,
    TestIntentHandler,
)


def build_skill(settings: Settings):
    sb = SkillBuilder()
    sb.skill_id = settings.alexa_skill_id

    sb.add_request_handler(LaunchRequestHandler())
    sb.add_request_handler(TestIntentHandler())
    sb.add_request_handler(HelpIntentHandler())
    sb.add_request_handler(CancelOrStopIntentHandler())
    sb.add_request_handler(SessionEndedRequestHandler())
    sb.add_exception_handler(CatchAllExceptionHandler())

    return sb.create()
