from maxapi.context import StatesGroup, State


class OnboardingStates(StatesGroup):
    waiting_consent = State()
    waiting_role = State()


class StudentStates(StatesGroup):
    choosing_teacher = State()
    choosing_category = State()
    entering_text = State()
    confirming = State()
    answering_clarification = State()
    searching_teacher = State()


class TeacherStates(StatesGroup):
    viewing_queue = State()
    working_ticket = State()
    entering_answer = State()
    requesting_clarification = State()
    entering_close_comment = State()
    offering_slots = State()
    uploading_kb = State()
    entering_kb_title = State()
