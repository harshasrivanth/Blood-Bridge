from pydantic import BaseModel, Field, EmailStr
from typing import Literal

BloodGroup = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]


class DonorCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    blood_group: BloodGroup
    phone: str = Field(pattern=r"^[6-9]\d{9}$")
    city: str = Field(min_length=2, max_length=100)
    is_available: bool = True
    consent_to_share_contact: bool = False


class DonorResponse(BaseModel):
    donor_id: int
    full_name: str
    blood_group: str
    city: str
    is_available: bool

    class Config:
        from_attributes = True


class BloodRequestCreate(BaseModel):
    patient_name: str = Field(min_length=2, max_length=100)
    patient_email: EmailStr
    blood_group: BloodGroup
    units_required: int = Field(ge=1, le=10)
    hospital_name: str = Field(min_length=2, max_length=150)
    city: str = Field(min_length=2, max_length=100)
    urgency: Literal["critical", "high", "medium", "low"] = "high"


class BloodRequestResponse(BaseModel):
    request_id: int
    message: str
