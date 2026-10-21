from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, func
from database import Base



class Donor(Base):
    __tablename__ = "donors"

    donor_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    blood_group = Column(String(5), nullable=False)
    phone = Column(String(15), nullable=True)
    city = Column(String(100), nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    consent_to_share_contact = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class BloodRequest(Base):
    __tablename__ = "blood_requests"

    request_id = Column(Integer, primary_key=True, index=True)
    patient_name = Column(String(100), nullable=False)
    patient_email = Column(String(254), nullable=False)
    blood_group = Column(String(5), nullable=False)
    units_required = Column(Integer, nullable=False)
    hospital_name = Column(String(150), nullable=False)
    city = Column(String(100), nullable=False)
    urgency = Column(String(20), nullable=False, default="high")
    status = Column(String(20), nullable=False, default="open")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class DonorOutreach(Base):
    __tablename__ = "donor_outreach"

    outreach_id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("blood_requests.request_id", ondelete="CASCADE"), nullable=False)
    donor_id = Column(Integer, ForeignKey("donors.donor_id", ondelete="CASCADE"), nullable=False)
    contacted_at = Column(DateTime, server_default=func.now(), nullable=False)
    outcome = Column(String(30), nullable=False, default="pending")


class Hospital(Base):
    __tablename__ = "hospitals"

    hospital_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), unique=True, nullable=False)
    is_demo = Column(Boolean, default=True, nullable=False)
    stamp_reference_text = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)