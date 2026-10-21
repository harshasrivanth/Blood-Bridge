import re
import json
import os
from contextlib import asynccontextmanager
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session
from pypdf import PdfReader
from io import BytesIO

from database import Base, engine, SessionLocal
import models
import schemas

from html import escape

load_dotenv()

DEMO_HOSPITALS = [
    {
        "name": "Hospital 1 - Vizag",
        "city": "Visakhapatnam",
        "marker": "BB-DEMO-VIZAG-ONLY",
    },
    {
        "name": "Hospital 2 - Vijayawada",
        "city": "Vijayawada",
        "marker": "BB-DEMO-VIJAYAWADA-ONLY",
    },
    {
        "name": "Hospital 3 - Hyderabad",
        "city": "Hyderabad",
        "marker": "BB-DEMO-HYDERABAD-ONLY",
    },
]

NO_DONORS_MESSAGE = (
    "No matching donors are available right now. "
    "Please contact the hospital blood bank for assistance."
)
SENT_MESSAGE = "Your request was received and matching donor information was emailed."
EMAIL_FAILED_MESSAGE = (
    "Your request was saved, but the email could not be sent. "
    "Please contact the hospital blood bank."
)


def initialize_database() -> None:
    """Create tables, apply additive migrations, and seed demo hospitals."""
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

        hospital_columns = {
            column["name"]
            for column in inspect(engine).get_columns("hospitals")
        }
        if "is_demo" not in hospital_columns:
            connection.execute(
                text(
                    "ALTER TABLE hospitals ADD COLUMN "
                    "is_demo BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
        if "stamp_reference_text" not in hospital_columns:
            connection.execute(
                text(
                    "ALTER TABLE hospitals "
                    "ADD COLUMN stamp_reference_text VARCHAR(100)"
                )
            )
        if "city" not in hospital_columns:
            connection.execute(
                text(
                    "ALTER TABLE hospitals ADD COLUMN "
                    "city VARCHAR(100) NOT NULL DEFAULT ''"
                )
            )

    db = SessionLocal()
    try:
        for item in DEMO_HOSPITALS:
            hospital = (
                db.query(models.Hospital)
                .filter(
                    func.lower(func.trim(models.Hospital.name))
                    == item["name"].lower()
                )
                .first()
            )
            if hospital is None:
                hospital = models.Hospital(name=item["name"])
                db.add(hospital)

            hospital.city = item["city"]
            hospital.is_demo = True
            hospital.stamp_reference_text = item["marker"]

        db.commit()
    except Exception:
        db.rollback()
        raise
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


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@app.get("/")
def home():
    return {"message": "Welcome to BloodBridge"}


@app.get("/health")
def health():
    return {"status": "running"}

@app.get("/hospitals")
def get_hospitals(
    city: str,
    db: Session = Depends(get_db),
):
    hospitals = (
        db.query(models.Hospital)
        .filter(
            func.lower(func.trim(models.Hospital.city))
            == city.strip().lower()
        )
        .order_by(models.Hospital.name.asc())
        .all()
    )

    return [
        {
            "hospital_id": hospital.hospital_id,
            "name": hospital.name,
            "city": hospital.city,
            "is_demo": hospital.is_demo,
        }
        for hospital in hospitals
    ]


@app.get("/db-health")
def database_health():
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")

    return {"database": "connected"}


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
    """Email a formatted list of available donors who consented to contact sharing."""
    script_url = os.getenv("GOOGLE_SCRIPT_URL")
    script_secret = os.getenv("GOOGLE_SCRIPT_SECRET")

    if not script_url or not script_secret:
        print("BloodBridge Google Apps Script email relay is not configured.")
        return False

    consenting_donors = [
        donor for donor in donors
        if donor.consent_to_share_contact and donor.is_available
    ]
    consenting_donors = remove_duplicate_donors(consenting_donors)

    if not consenting_donors:
        print("BloodBridge email skipped: no consenting available donors.")
        return False

    rows_html = []
    text_rows = []

    for serial, donor in enumerate(consenting_donors, start=1):
        name = escape(donor.full_name or "Name unavailable")
        donor_city = escape(donor.city or "City unavailable")
        phone = escape(donor.phone or "Contact unavailable")

        rows_html.append(
            "<tr>"
            f'<td style="padding:10px;border:1px solid #dbe3ef;text-align:center">{serial}</td>'
            f'<td style="padding:10px;border:1px solid #dbe3ef">{name}</td>'
            f'<td style="padding:10px;border:1px solid #dbe3ef">{donor_city}</td>'
            f'<td style="padding:10px;border:1px solid #dbe3ef">{phone}</td>'
            "</tr>"
        )
        text_rows.append(
            f"{serial}. {donor.full_name or 'Name unavailable'} | "
            f"{donor.city or 'City unavailable'} | "
            f"{donor.phone or 'Contact unavailable'}"
        )

    blood_group = escape(request.blood_group or "N/A")
    request_city = escape(request.city or "N/A")
    units = request.units_required
    subject = f"BloodBridge: {request.blood_group} donor matches"

    html_body = f"""
    <div style="font-family:Arial,sans-serif;color:#243047;max-width:720px;margin:auto;line-height:1.6">
      <div style="background:#1758c7;color:#fff;padding:22px;border-radius:10px 10px 0 0">
        <h1 style="margin:0">BloodBridge</h1>
        <p style="margin:6px 0 0">Connecting people who need blood with willing donors</p>
      </div>
      <div style="padding:24px;border:1px solid #dbe3ef">
        <h2 style="color:#1758c7">Matching donor information</h2>
        <p>The prototype document check passed and potential donor profiles matching the requested blood group and city were found.</p>
        <table style="width:100%;border-collapse:collapse;margin:18px 0">
          <tr style="background:#eef4ff">
            <td style="padding:10px"><strong>Blood group needed</strong></td>
            <td style="padding:10px">{blood_group}</td>
          </tr>
          <tr>
            <td style="padding:10px"><strong>City</strong></td>
            <td style="padding:10px">{request_city}</td>
          </tr>
          <tr style="background:#eef4ff">
            <td style="padding:10px"><strong>Units requested</strong></td>
            <td style="padding:10px">{units}</td>
          </tr>
        </table>
        <h3>Donor contact list</h3>
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <thead><tr style="background:#1758c7;color:#fff">
            <th style="padding:10px;border:1px solid #dbe3ef">S. No.</th>
            <th style="padding:10px;border:1px solid #dbe3ef">Donor Name</th>
            <th style="padding:10px;border:1px solid #dbe3ef">City</th>
            <th style="padding:10px;border:1px solid #dbe3ef">Phone Number</th>
          </tr></thead>
          <tbody>{''.join(rows_html)}</tbody>
        </table>
        <p style="margin-top:24px">Thank you for using <strong>BloodBridge</strong>. We hope this connection helps you reach the support you need.</p>
        <div style="background:#fff7e6;border:1px solid #f4d28b;padding:14px;border-radius:8px;font-size:13px">
          <strong>Important:</strong> These are potential donor matches only. Hospital or blood-bank staff must confirm donor eligibility, blood compatibility, and availability before any clinical decision. This prototype email does not guarantee blood availability.
        </div>
      </div>
      <p style="font-size:12px;color:#65728a;text-align:center;padding:12px">BloodBridge · Prototype build · Thank you</p>
    </div>
    """

    plain_body = (
        "BloodBridge - Matching donor information\n\n"
        f"Blood group needed: {request.blood_group}\n"
        f"City: {request.city}\n"
        f"Units requested: {request.units_required}\n\n"
        "S. No. | Donor Name | City | Phone Number\n"
        + "\n".join(text_rows)
        + "\n\nThank you for using BloodBridge.\n\n"
        "Important: Hospital or blood-bank staff must confirm donor eligibility, "
        "compatibility, and availability before any clinical decision."
    )

    payload = {
        "secret": script_secret,
        "to": to_email,
        "subject": subject,
        "body": plain_body,
        "htmlBody": html_body,
    }
    data = json.dumps(payload).encode("utf-8")
    relay_request = Request(
        script_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(relay_request, timeout=25) as response:
            response_body = response.read().decode("utf-8")
        result = json.loads(response_body)
        if result.get("success") is True:
            return True
        print("BloodBridge email relay rejected the request.")
        return False
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        # Do not log secrets, patient email, or donor details.
        print(
            f"BloodBridge email relay failed: {type(exc).__name__}, "
            f"code={getattr(exc, 'code', 'N/A')}"
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


@app.post("/requests", response_model=schemas.BloodRequestResponse)
async def create_blood_request(
    patient_name: str = Form(..., min_length=2, max_length=100),
    patient_email: str = Form(...),
    blood_group: str = Form(...),
    units_required: int = Form(..., ge=1, le=10),
    hospital_name: str = Form(..., min_length=2, max_length=150),
    city: str = Form(..., min_length=2, max_length=100),
    urgency: str = Form("high"),
    hospital_document: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Prototype gate: check PDF text against registered demo hospital data before email."""
    from email_validator import validate_email, EmailNotValidError

    try:
        validated_email = validate_email(patient_email, check_deliverability=False).normalized
    except EmailNotValidError:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")

    allowed_groups = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    if blood_group.strip().upper() not in allowed_groups:
        raise HTTPException(status_code=422, detail="Select a valid blood group.")
    if urgency not in {"critical", "high", "medium", "low"}:
        raise HTTPException(status_code=422, detail="Select a valid urgency.")

    requested_hospital = hospital_name.strip()
    hospital = (
        db.query(models.Hospital)
        .filter(
            func.lower(func.trim(models.Hospital.name)) == requested_hospital.lower(),
            func.lower(func.trim(models.Hospital.city)) == city.strip().lower(),
            models.Hospital.is_demo.is_(True),
        )
        .first()
    )
    if hospital is None:
        raise HTTPException(
            status_code=400,
            detail="This demo version accepts requests for the registered demo hospital only.",
        )

    # This prototype accepts a searchable PDF, not photos or scanned image-only PDFs.
    # PDF text is checked against registered demo markers; this is NOT image matching
    # or real-world hospital authenticity verification.
    if hospital_document.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Upload the matching hospital demo PDF for the selected city.")
    document_bytes = await hospital_document.read()
    if not document_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")
    if len(document_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF must be 5 MB or smaller.")

    try:
        pdf = PdfReader(BytesIO(document_bytes))
        raw_text = "\n".join(
            page.extract_text() or ""
            for page in pdf.pages
        )
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Could not read this PDF. Upload the provided demo sample.",
        )

    # Normalize case, punctuation, and line breaks before checking markers.
    def normalize_pdf_text(value: str) -> str:
        return " ".join(re.findall(r"[A-Z0-9]+", value.upper()))

    document_text = normalize_pdf_text(raw_text)
    stamp_marker = normalize_pdf_text(
        hospital.stamp_reference_text or ""
    )
    hospital_marker = normalize_pdf_text(hospital.name)
    demo_marker = normalize_pdf_text("DEMO DOCUMENT")

    required_markers = [
        hospital_marker,
        demo_marker,
        stamp_marker,
    ]

    if not all(required_markers) or not all(
        marker in document_text
        for marker in required_markers
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Demo PDF verification failed. Upload the matching searchable PDF "
                "for the selected hospital, including its registered demo marker. "
                "No donor email was sent."
            ),
        )

    new_request = models.BloodRequest(
        patient_name=patient_name.strip(),
        patient_email=validated_email,
        blood_group=blood_group.strip().upper(),
        units_required=units_required,
        hospital_name=hospital.name,
        city=city.strip(),
        urgency=urgency,
        status="open",
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    donors = (
        db.query(models.Donor)
        .filter(
            func.upper(func.trim(models.Donor.blood_group)) == new_request.blood_group,
            func.lower(func.trim(models.Donor.city)) == new_request.city.lower(),
            models.Donor.is_available.is_(True),
            models.Donor.consent_to_share_contact.is_(True),
        )
        .order_by(models.Donor.donor_id.asc())
        .all()
    )
    donors = remove_duplicate_donors(donors)

    if not donors:
        return {
            "request_id": new_request.request_id,
            "message": "Demo document check passed, but no matching consenting donors are available.",
        }

    if send_donor_email(new_request.patient_email, new_request, donors):
        return {
            "request_id": new_request.request_id,
            "message": "Demo document check passed. Matching donor information was emailed.",
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
