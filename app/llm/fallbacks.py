from app.models.state import LessonStage

FALLBACK_RESPONSES: dict[LessonStage, str] = {
    LessonStage.GREETING: "Hi there! I'm Charlie the fox! Ready to learn some cool words today?",
    LessonStage.INTRODUCE_WORD: "Let's learn a new word! Are you ready?",
    LessonStage.REPEAT_WORD: "Can you say the word? Try it!",
    LessonStage.EXERCISE: "Hmm, let me think... Can you try again?",
    LessonStage.FEEDBACK: "Great job trying! Let's keep going!",
    LessonStage.REVIEW: "We learned so many words today! Say them with me!",
    LessonStage.FAREWELL: "Bye bye! You did amazing today! See you next time!",
    LessonStage.COMPLETED: "See you next time!",
}
