
import os
import smtplib
from contextlib import asynccontextmanager
from email.message import EmailMessage

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from database import Base, engine, SessionLocal
import models
import schemas

load_dotenv()

DEMO_HOSPITAL_NAME = "My hospital"

NO_DONORS_MESSAGE = (
    "No matching donors are available right now. "
    "Please contact the hospital blood bank for assistance."
)

SENT_MESSAGE = "Donors list is sent to registered mail."

EMAIL_FAILED_MESSAGE = (
    "We couldn't send the email right now. Please try again later "
    "or contact the hospital blood bank."
)


def initialize_database() -> None:
    """Create tables and apply safe additive migrations."""
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        donor_columns = {
            column["name"]
            for column in inspect(engine).get_columns("donors")
        }

        if "consent_to_share_contact" not in donor_columns:
            connection.execute(
                text(
                    "ALTER TABLE donors ADD COLUMN "
                    "consent_to_share_contact BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )

        request_columns = {
            column["name"]
            for column in inspect(engine).get_columns("blood_requests")
        }

        if "patient_email" not in request_columns:
            connection.execute(
                text(
                    "ALTER TABLE blood_requests "
                    "ADD COLUMN patient_email VARCHAR(254)"
                )
            )

    db = SessionLocal()

    try:
        hospital = (
            db.query(models.Hospital)
            .filter(
                func.lower(models.Hospital.name)
                == DEMO_HOSPITAL_NAME.lower()
            )
            .first()
        )

        if hospital is None:
            db.add(
                models.Hospital(
                    name=DEMO_HOSPITAL_NAME,
                    is_demo=True,
                )
            )
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="BloodBridge API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "https://harshasrivanth.github.io",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def home():
    return {"message": "Welcome to BloodBridge"}


@app.get("/health")
def health():
    return {"status": "running"}


@app.get("/db-health")
def database_health():
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")

    return {"database": "connected"}


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def remove_duplicate_donors(
    donors: list[models.Donor],
) -> list[models.Donor]:
    """Keep only one donor record per normalized phone number."""
    unique_donors = []
    seen_contacts = set()

    for donor in donors:
        # Normalize the phone number to digits for comparison.
        contact = "".join(
            character
            for character in (donor.phone or "")
            if character.isdigit()
        )

        if contact:
            if contact in seen_contacts:
                continue

            seen_contacts.add(contact)

        unique_donors.append(donor)

    return unique_donors


def send_donor_email(
    to_email: str,
    request: models.BloodRequest,
    donors: list[models.Donor],
) -> bool:
    """Email matching donor profiles whose owners consented."""
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_APP_PASSWORD")

    if not smtp_email or not smtp_password:
        print("BloodBridge email delivery is not configured.")
        return False

    message = EmailMessage()

    message["Subject"] = (
        f"BloodBridge: matching donors for request "
        f"#{request.request_id}"
    )

    message["From"] = smtp_email
    message["To"] = to_email

    donor_rows = []

    for donor in donors:
        donor_rows.append(
            "\n".join(
                [
                    f"Name: {donor.full_name}",
                    f"Blood group: {donor.blood_group}",
                    f"City: {donor.city}",
                    f"Contact: {donor.phone or 'Contact unavailable'}",
                ]
            )
        )

    message.set_content(
        "BloodBridge found donor profiles matching the "
        "requested blood group and city.\n\n"
        f"Request ID: {request.request_id}\n"
        f"Blood group: {request.blood_group}\n"
        f"City: {request.city}\n"
        f"Units requested: {request.units_required}\n\n"
        + "\n\n---\n\n".join(donor_rows)
        + "\n\nImportant: These are preliminary directory matches only. "
        "Hospital or blood-bank staff must confirm donor eligibility, "
        "compatibility, and availability before any clinical decision."
    )

    try:
        with smtplib.SMTP(
            "smtp.gmail.com",
            587,
            timeout=20,
        ) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(message)

        return True

    except (OSError, smtplib.SMTPException) as exc:
        # Never print passwords or donor contact details.
        print(
            "BloodBridge email delivery failed: "
            f"{type(exc).__name__}"
        )
        return False


@app.post(
    "/donors",
    response_model=schemas.DonorResponse,
)
def create_donor(
    donor: schemas.DonorCreate,
    db: Session = Depends(get_db),
):
    new_donor = models.Donor(
        full_name=donor.full_name.strip(),
        blood_group=donor.blood_group.strip().upper(),
        phone=donor.phone,
        city=donor.city.strip(),
        is_available=donor.is_available,
        # Consent must be explicitly provided by the donor.
        consent_to_share_contact=donor.consent_to_share_contact,
    )

    db.add(new_donor)
    db.commit()
    db.refresh(new_donor)

    return new_donor


@app.get("/donors")
def donors_private():
    # Do not expose the donor directory publicly.
    raise HTTPException(
        status_code=404,
        detail="Not found",
    )


@app.post(
    "/requests",
    response_model=schemas.BloodRequestResponse,
)
def create_blood_request(
    request: schemas.BloodRequestCreate,
    db: Session = Depends(get_db),
):
    requested_hospital = request.hospital_name.strip()

    hospital = (
        db.query(models.Hospital)
        .filter(
            func.lower(func.trim(models.Hospital.name))
            == requested_hospital.lower(),
            models.Hospital.is_demo.is_(True),
        )
        .first()
    )

    if hospital is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "This demo version accepts requests for the "
                "registered demo hospital only."
            ),
        )

    new_request = models.BloodRequest(
        patient_name=request.patient_name.strip(),
        patient_email=str(request.patient_email),
        blood_group=request.blood_group.strip().upper(),
        units_required=request.units_required,
        hospital_name=hospital.name,
        city=request.city.strip(),
        urgency=request.urgency,
        status="open",
    )

    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    # Match blood group, city, availability, and explicit consent.
    donors = (
        db.query(models.Donor)
        .filter(
            func.upper(func.trim(models.Donor.blood_group))
            == new_request.blood_group.upper(),
            func.lower(func.trim(models.Donor.city))
            == new_request.city.strip().lower(),
            models.Donor.is_available.is_(True),
            models.Donor.consent_to_share_contact.is_(True),
        )
        .order_by(models.Donor.donor_id.asc())
        .all()
    )

    # Remove duplicate contact numbers before sending the email.
    donors = remove_duplicate_donors(donors)

    if not donors:
        return {
            "request_id": new_request.request_id,
            "message": NO_DONORS_MESSAGE,
        }

    if send_donor_email(
        new_request.patient_email,
        new_request,
        donors,
    ):
        return {
            "request_id": new_request.request_id,
            "message": SENT_MESSAGE,
        }

    return {
        "request_id": new_request.request_id,
        "message": EMAIL_FAILED_MESSAGE,
    }


@app.get("/requests")
def requests_private():
    # Request records contain personal information.
    raise HTTPException(
        status_code=404,
        detail="Not found",
    )


@app.get("/requests/{request_id}/donors")
def matches_private(request_id: int):
    # Donor details are not exposed through a public endpoint.
    raise HTTPException(
        status_code=404,
        detail="Not found",
    )
