from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    task: str
    owner: str = ""
    deadline: str = ""


class MeetingMinutes(BaseModel):
    title: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)


class GenerateNotesResponse(BaseModel):
    id: int
    transcript: str
    notes: MeetingMinutes
    created_at: str

