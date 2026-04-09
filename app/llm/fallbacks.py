from app.models.state import LessonStage

FALLBACK_RESPONSES: dict[LessonStage, str] = {
    LessonStage.GREETING: "Hi there! I'm Charlie the fox! Ready to learn some cool words today?",
    LessonStage.INTRODUCE_WORD: "Let's learn a new word! Are you ready?",
    LessonStage.EXERCISE: "Hmm, let me think... Can you try again?",
    LessonStage.FEEDBACK: "Great job trying! Let's keep going!",
    LessonStage.FAREWELL: "Bye bye! You did amazing today! See you next time!",
    LessonStage.COMPLETED: "See you next time!",
}
