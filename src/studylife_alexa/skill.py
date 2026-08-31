from ask_sdk_core.skill_builder import SkillBuilder

from studylife_alexa.config import Settings
from studylife_alexa.handlers import (
    CancelOrStopIntentHandler,
    CatchAllExceptionHandler,
    CourseGoalsIntentHandler,
    CoursesIntentHandler,
    CreateNoteIntentHandler,
    FallbackIntentHandler,
    HelpIntentHandler,
    LaunchRequestHandler,
    NavigateHomeIntentHandler,
    NextSessionIntentHandler,
    NotesOverviewIntentHandler,
    ProgramProgressIntentHandler,
    RecentSessionsIntentHandler,
    SearchNotesIntentHandler,
    SessionEndedRequestHandler,
    StudyProgramsIntentHandler,
    StudyTimeIntentHandler,
    TestIntentHandler,
    TimerStatusIntentHandler,
)


def build_skill(settings: Settings):
    sb = SkillBuilder()
    sb.skill_id = settings.alexa_skill_id

    sb.add_request_handler(LaunchRequestHandler())
    sb.add_request_handler(TestIntentHandler())
    sb.add_request_handler(CoursesIntentHandler())
    sb.add_request_handler(TimerStatusIntentHandler())
    sb.add_request_handler(StudyTimeIntentHandler())
    sb.add_request_handler(RecentSessionsIntentHandler())
    sb.add_request_handler(NextSessionIntentHandler())
    sb.add_request_handler(CourseGoalsIntentHandler())
    sb.add_request_handler(StudyProgramsIntentHandler())
    sb.add_request_handler(ProgramProgressIntentHandler())
    sb.add_request_handler(SearchNotesIntentHandler())
    sb.add_request_handler(NotesOverviewIntentHandler())
    sb.add_request_handler(CreateNoteIntentHandler())
    sb.add_request_handler(HelpIntentHandler())
    sb.add_request_handler(NavigateHomeIntentHandler())
    sb.add_request_handler(FallbackIntentHandler())
    sb.add_request_handler(CancelOrStopIntentHandler())
    sb.add_request_handler(SessionEndedRequestHandler())
    sb.add_exception_handler(CatchAllExceptionHandler())

    return sb.create()
